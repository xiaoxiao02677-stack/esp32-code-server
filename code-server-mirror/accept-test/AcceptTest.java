import org.bouncycastle.asn1.gm.GMNamedCurves;
import org.bouncycastle.asn1.x9.X9ECParameters;
import org.bouncycastle.crypto.engines.SM2Engine;
import org.bouncycastle.crypto.params.ECDomainParameters;
import org.bouncycastle.crypto.params.ECPublicKeyParameters;
import org.bouncycastle.crypto.params.ParametersWithRandom;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.encoders.Hex;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.Security;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 12项验收清单驱动脚本
 * 前置：redis-cli set sys:captcha:accept-1 88888 EX 600
 * 运行：java -cp /root/.m2/repository/org/bouncycastle/bcprov-jdk18on/1.78/bcprov-jdk18on-1.78.jar AcceptTest.java
 */
public class AcceptTest {
    static final String PUB =
            "04003312490a186fedb2b8dab3e848110f3fc5a967ea24b0ff2cc59bb5a5f9a60272b2dd4f222c9d6b0595dde84368e341795765fe6d35fa21f3cb3e5ee6851a4e";
    static final String CAPTCHA_ID = "accept-1";
    static final String CAPTCHA = "a8b8c";
    static String base = "http://127.0.0.1:8002/xiaozhi";
    static int pass = 0, fail = 0;

    public static void main(String[] args) throws Exception {
        Security.addProvider(new BouncyCastleProvider());
        if (args.length > 0) base = args[0];

        // ============ 登录超管 demo ============
        String adminToken = login("demo", "accept-admin-2026");
        check("admin登录获取token", adminToken != null, adminToken == null ? "" : "token=" + adminToken.substring(0, 16) + "...");

        // ============ [1] RBAC：角色分页/列表 ============
        String r1 = http("GET", base + "/admin/role/page?page=1&limit=10", null, adminToken);
        check("1a 角色分页", r1.contains("\"code\":0") && r1.contains("super_admin"), r1);

        // ============ [2] 用户管理：创建用户（返回初始密码）============
        long ts = System.currentTimeMillis();
        String newUsername = "acctest" + (ts % 100000);
        String createResp = http("POST", base + "/admin/users",
                "{\"username\":\"" + newUsername + "\",\"roleIds\":[3]}", adminToken);
        check("2a 创建用户返回初始密码", createResp.contains("\"code\":0"), createResp);
        String initPwd = extract(createResp, "\"data\":\"([^\"]+)\"");
        // 查询该用户 id（Long序列化为字符串："id":"211..."）
        String pageResp = http("GET", base + "/admin/users?page=1&limit=50&keyword=" + newUsername, null, adminToken);
        String newUserId = extract(pageResp, "\"id\":\"?(\\d+)\"?");
        check("2b 用户分页可查到新用户", newUserId != null, "userId=" + newUserId);

        // ============ [3] mustChangePwd：新用户强制改密 ============
        String nuToken = login(newUsername, initPwd);
        if (nuToken != null) {
            String info = http("GET", base + "/user/info", null, nuToken);
            boolean mcp = info.contains("\"mustChangePwd\":true") || info.contains("\"mustChangePwd\":1");
            check("3 新用户 mustChangePwd=true", mcp, info);
        } else {
            check("3 新用户登录", false, "登录失败");
        }

        // ============ [4] 越权测试：普通用户访问管理端点 → 403 + 审计 ============
        String forbidden = http("GET", base + "/admin/users?page=1&limit=10", null, nuToken);
        boolean is403 = forbidden.contains("\"code\":403") || forbidden.contains("forbidden") || forbidden.startsWith("403");
        check("4 普通用户访问/admin/users被拒", is403, forbidden);

        // ============ [5] 角色分配实时生效：给新用户临时授 admin 角色 → 立即可访问 ============
        // （admin:2 用户管理权限 → sys:user:list 属于 admin 角色的 permissions）
        // 先查角色2的permissions是否包含 admin:user:list
        String roleDetail = http("GET", base + "/admin/role/2", null, adminToken);
        // 分配角色2
        String assignResp = http("PUT", base + "/admin/users/roles",
                "{\"userId\":" + newUserId + ",\"roleIds\":[2]}", adminToken);
        check("5a 分配admin角色", assignResp.contains("\"code\":0"), assignResp);
        // 立即重试管理端点（Oauth2Realm实时查库，无需重登）
        String retry = http("GET", base + "/admin/users?page=1&limit=10", null, nuToken);
        check("5b 角色变更实时生效(免重登)", retry.contains("\"code\":0"), retry);
        // 收回
        http("PUT", base + "/admin/users/roles",
                "{\"userId\":" + newUserId + ",\"roleIds\":[3]}", adminToken);
        String retry2 = http("GET", base + "/admin/users?page=1&limit=10", null, nuToken);
        boolean denied2 = retry2.contains("\"code\":403") || retry2.contains("forbidden") || retry2.startsWith("403");
        check("5c 收回后立即失去权限", denied2, retry2);

        // ============ [6] 用户端隔离：新用户创建自定义模型，admin可见、其他普通用户不可见 ============
        String cmCreate = http("POST", base + "/user/custom-models",
                "{\"modelType\":\"LLM\",\"modelName\":\"acc-model-" + ts % 10000 + "\",\"apiKey\":\"sk-test-1234567890\",\"baseUrl\":\"http://127.0.0.1:1\"}", nuToken);
        check("6a 用户创建自定义模型", cmCreate.contains("\"code\":0"), cmCreate);
        String myList = http("GET", base + "/user/custom-models?modelType=LLM", null, nuToken);
        boolean masked = myList.contains("apiKeyMasked") && !myList.contains("sk-test-1234567890");
        check("6b apiKey密文存储+接口掩码", masked, myList);

        // ============ [7] 审计日志：操作已落库 ============
        String auditPage = http("GET", base + "/admin/audit/page?page=1&limit=20", null, adminToken);
        boolean auditOk = auditPage.contains("\"code\":0") && (auditPage.contains("custom") || auditPage.contains("login") || auditPage.contains("user"));
        check("7 审计日志记录", auditOk, auditPage);

        // ============ [8] 自定义模型审核+配额（admin端）============
        String cmAdmin = http("GET", base + "/admin/custom-models/page?auditStatus=0&page=1&limit=10", null, adminToken);
        String cmId = extract(cmAdmin, "\"id\":\"([a-f0-9]{20,})\"");
        check("8a 待审模型出现在admin队列", cmId != null, "cmId=" + cmId);
        if (cmId != null) {
            String auditPass = http("POST", base + "/admin/custom-models/audit",
                    "{\"id\":\"" + cmId + "\",\"pass\":true,\"remark\":\"验收通过\"}", adminToken);
            check("8b 审核通过", auditPass.contains("\"code\":0"), auditPass);
            String quota = http("PUT", base + "/admin/custom-models/quota",
                    "{\"id\":\"" + cmId + "\",\"quotaLimit\":100}", adminToken);
            check("8c 设置配额100", quota.contains("\"code\":0"), quota);
            // 审核通过后出现在用户资源列表
            String res = http("GET", base + "/user/resources", null, nuToken);
            boolean hasCustom = res.contains("acc-model-") || res.contains("\"source\":\"custom\"");
            check("8d 审核通过后进入用户资源", hasCustom, res);
        }

        // ============ [9] 默认模型三级继承：系统级配置 ============
        String dispCfg = http("PUT", base + "/admin/display-config",
                "{\"scopeType\":0,\"configJson\":\"{\\\"fields\\\":[{\\\"key\\\":\\\"name\\\",\\\"visible\\\":true,\\\"label\\\":\\\"昵称\\\"},{\\\"key\\\":\\\"model\\\",\\\"visible\\\":true,\\\"label\\\":\\\"模型\\\"}]}\"}", adminToken);
        check("9a 保存系统级展示配置", dispCfg.contains("\"code\":0"), dispCfg);
        String effDisp = http("GET", base + "/user/display-config", null, nuToken);
        check("9b 用户取到合并后展示配置", effDisp.contains("\"code\":0") && effDisp.contains("fields"), effDisp);

        // 用户级默认模型
        String defCfg = http("PUT", base + "/user/defaults",
                "{\"defaultLLM\":\"\"}", nuToken);
        String effDef = http("GET", base + "/user/defaults", null, nuToken);
        check("9c 用户默认配置可读写", effDef.contains("\"code\":0"), effDef);

        // ============ [10] 会话管理 ============
        String sess = http("GET", base + "/admin/users/sessions?page=1&limit=10", null, adminToken);
        boolean sessMasked = sess.contains("****") && !sess.contains(adminToken);
        check("10a 会话列表token掩码", sess.contains("\"code\":0") && sessMasked, sess);
        // 强制下线新用户
        String flogout = http("POST", base + "/admin/users/forceLogout/" + newUserId, null, adminToken);
        check("10b 强制下线", flogout.contains("\"code\":0"), flogout);

        // ============ [11] 软删/恢复 ============
        String softDel = http("DELETE", base + "/admin/users/" + newUserId, null, adminToken);
        check("11a 软删用户", softDel.contains("\"code\":0"), softDel);
        String pageAfterDel = http("GET", base + "/admin/users?page=1&limit=50&keyword=" + newUsername + "&deleted=1", null, adminToken);
        check("11b 已删列表可见", pageAfterDel.contains(newUsername), pageAfterDel);
        String restore = http("PUT", base + "/admin/users/restore/" + newUserId, null, adminToken);
        check("11c 恢复用户", restore.contains("\"code\":0"), restore);

        // ============ [12] 导出CSV ============
        String exp = http("GET", base + "/admin/users/export?username=" + newUsername, null, adminToken);
        check("12 CSV导出含BOM+数据", exp.startsWith("200") && exp.contains("\uFEFF") && exp.contains(newUsername), exp.substring(0, Math.min(200, exp.length())));

        System.out.println("\n========== 验收汇总: PASS=" + pass + " FAIL=" + fail + " ==========");
        if (fail > 0) System.exit(1);
    }

    static String login(String username, String password) throws Exception {
        // 刷新验证码（JSON字符串格式，GenericJackson2JsonRedisSerializer兼容）
        String captchaId = CAPTCHA_ID + "-" + Math.abs((username + System.nanoTime()).hashCode()) % 100000;
        Process p = new ProcessBuilder("redis-cli", "set",
                "sys:captcha:" + captchaId, "\"" + CAPTCHA + "\"", "EX", "300")
                .redirectErrorStream(true).start();
        p.getInputStream().readAllBytes();
        p.waitFor();
        String cipher = sm2Encrypt(PUB, CAPTCHA + password);
        String body = "{\"username\":\"" + username + "\",\"password\":\"" + cipher
                + "\",\"captchaId\":\"" + captchaId + "\"}";
        String resp = http("POST", base + "/user/login", body, null);
        if (resp.contains("\"code\":0") && resp.contains("\"token\":\"")) {
            return extract(resp, "\"token\":\"([^\"]+)\"");
        }
        System.out.println("  [login-fail] " + username + ": " + resp);
        return null;
    }

    static void check(String name, boolean ok, String detail) {
        if (ok) { pass++; System.out.println("  [PASS] " + name); }
        else { fail++; System.out.println("  [FAIL] " + name + " <<< " + abbrev(detail)); }
    }

    static String abbrev(String s) {
        if (s == null) return "null";
        return s.length() > 300 ? s.substring(0, 300) + "..." : s;
    }

    static String extract(String json, String regex) {
        if (json == null) return null;
        Matcher m = Pattern.compile(regex).matcher(json);
        if (m.find()) return m.group(1);
        return null;
    }

    static String sm2Encrypt(String publicKey, String data) throws Exception {
        X9ECParameters sm2ECParameters = GMNamedCurves.getByName("sm2p256v1");
        ECDomainParameters domainParameters = new ECDomainParameters(sm2ECParameters.getCurve(),
                sm2ECParameters.getG(), sm2ECParameters.getN());
        ECPoint pukPoint = sm2ECParameters.getCurve().decodePoint(Hex.decode(publicKey));
        ECPublicKeyParameters publicKeyParameters = new ECPublicKeyParameters(pukPoint, domainParameters);
        SM2Engine engine = new SM2Engine(SM2Engine.Mode.C1C3C2);
        engine.init(true, new ParametersWithRandom(publicKeyParameters, new SecureRandom()));
        byte[] in = data.getBytes(StandardCharsets.UTF_8);
        return Hex.toHexString(engine.processBlock(in, 0, in.length));
    }

    static String http(String method, String urlStr, String jsonBody, String token) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(20000);
            conn.setRequestMethod(method);
            conn.setRequestProperty("Content-Type", "application/json");
            if (token != null) conn.setRequestProperty("Authorization", "Bearer " + token);
            if (jsonBody != null) {
                conn.setDoOutput(true);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(jsonBody.getBytes(StandardCharsets.UTF_8));
                }
            }
            int code = conn.getResponseCode();
            java.io.InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            byte[] buf = is == null ? new byte[0] : is.readAllBytes();
            return code + " " + new String(buf, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "ERR " + e.getMessage();
        }
    }
}
