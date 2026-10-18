package xiaozhi.common.utils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;

import net.sourceforge.pinyin4j.PinyinHelper;
import net.sourceforge.pinyin4j.format.HanyuPinyinOutputFormat;

import org.junit.jupiter.api.Test;

/**
 * 唤醒词汉字→无调拼音转换契约（固件 MultiNet 命令词格式）。
 *
 * <p>断言口径（已定稿，勿随意改动）：
 * <ul>
 *   <li>拼音上限 60：{@code isFirmwareSafe} 60 通过、61 起拒（引擎硬上限 63，
 *       61~62 被产品侧提前拦住是预期，不是 bug）；</li>
 *   <li>整条拼音串 len &gt;= 2：「哦」(len=1) 拒、「哦哦」("e e", len=3) 通过——
 *       长度判的是 join 后整串，不是单 token；</li>
 *   <li>{@code isFirmwareSafe} 仅 [a-z ]，不许数字；</li>
 *   <li>{@code knownLimitation_} 前缀两条是<b>设计如此</b>（手填拼音逃生通道），
 *       放行才算对，别改成"应拦截"。</li>
 * </ul>
 *
 * <p><b>维护提醒</b>：PHRASE_OVERRIDES / SYLLABLE_ALIASES 是纯数据表、不参与编译期
 * 检查，任何改动必须重跑本测试（{@code mvn -o test -Dtest=WakeWordPinyinUtilsTest}）。
 */
public class WakeWordPinyinUtilsTest {

    // ---------- A. 短语表 / 基础转换（PASS） ----------

    @Test
    public void testBasicConversions() {
        assertEquals("ni hao xiao he", WakeWordPinyinUtils.toPinyin("你好小禾"));
        assertEquals("gui gui", WakeWordPinyinUtils.toPinyin("鬼鬼"), "叠字");
        assertEquals("zao shang hao xiao you zi", WakeWordPinyinUtils.toPinyin("早上好小优子"), "6 音节基线");
    }

    @Test
    public void testPhraseOverrides() {
        // PHRASE_OVERRIDES 多音字短语覆盖表（当前 32 条）
        assertEquals("chong qing", WakeWordPinyinUtils.toPinyin("重庆"));
        assertEquals("yin yue", WakeWordPinyinUtils.toPinyin("音乐"));
        assertEquals("yin hang", WakeWordPinyinUtils.toPinyin("银行"));
        assertEquals("xing zhang", WakeWordPinyinUtils.toPinyin("行长"));
        // R4 补齐的 7 个多音词（历史上曾错，防回归）
        assertEquals("chang jiang", WakeWordPinyinUtils.toPinyin("长江"));
        assertEquals("gui huan", WakeWordPinyinUtils.toPinyin("归还"));
        assertEquals("xia men", WakeWordPinyinUtils.toPinyin("厦门"));
        assertEquals("tiao jie", WakeWordPinyinUtils.toPinyin("调解"));
        assertEquals("pan yu", WakeWordPinyinUtils.toPinyin("番禺"));
        assertEquals("lu an", WakeWordPinyinUtils.toPinyin("六安"));
        assertEquals("shan xian", WakeWordPinyinUtils.toPinyin("单县"));
    }

    @Test
    public void testThreeCharPhraseOrdering() {
        // 人工排序约定：3 字词必须排在构成前缀的 2 字词（"什么"）之前，
        // 否则 matchPhrase 首个 startsWith 命中会把「为什么」截成 "wei shen"+"me" 错位。
        assertEquals("wei shen me", WakeWordPinyinUtils.toPinyin("为什么"));
        assertEquals("wei shen me yao", WakeWordPinyinUtils.toPinyin("为什么要"));
    }

    // ---------- B. 音节别名（ng→en / lue→lve / nue→nve，来自 SYLLABLE_ALIASES，非 pinyin4j 原生） ----------

    @Test
    public void testSyllableAliases() {
        // 嗯→en：对齐旧固件内置字表 board.cc {"嗯","en"}，拒绝即功能回退
        assertEquals("en", WakeWordPinyinUtils.toPinyin("嗯"));
        assertEquals("en heng", WakeWordPinyinUtils.toPinyin("嗯哼"));
        // pinyin4j 原始输出是 lu:e/nu:e（WITH_V 下），lve/nve 由别名表归一——换库/升级这条会第一个炸
        assertEquals("lve", WakeWordPinyinUtils.toPinyin("略"));
        assertEquals("nve", WakeWordPinyinUtils.toPinyin("虐"));
        assertEquals("lve nve", WakeWordPinyinUtils.toPinyin("略虐"));
    }

    // ---------- C. ü 全语境与多候选取 [0] ----------

    @Test
    public void testUmlautContexts() {
        // FORMAT 设了 WITH_V（WakeWordPinyinUtils 静态块）——回退默认 WITH_U_AND_COLON
        // 会产出 lu:e4 → 含 ':' 和数字 → isFirmwareSafe 拒 → 词被静默丢掉
        assertEquals("nv lv lv", WakeWordPinyinUtils.toPinyin("女绿旅"));
        assertEquals("xue yue jue que", WakeWordPinyinUtils.toPinyin("学月决缺"));
        assertEquals("ju qu xu", WakeWordPinyinUtils.toPinyin("句去虚"));
        assertEquals("nv", WakeWordPinyinUtils.toPinyin("nü"), "手填 ü 逃生通道转 v");
    }

    @Test
    public void testMultiCandidateTakesFirst() throws Exception {
        // 绿 的原始候选是 [lv, lu]，必须取 [0]；取 [1] 得 lu（错，且无报错）
        Field f = WakeWordPinyinUtils.class.getDeclaredField("FORMAT");
        f.setAccessible(true);
        HanyuPinyinOutputFormat fmt = (HanyuPinyinOutputFormat) f.get(null);
        String[] cands = PinyinHelper.toHanyuPinyinStringArray('绿', fmt);
        assertTrue(cands != null && cands.length >= 2, "绿 应有多候选");
        assertTrue(cands[0].startsWith("lv"), "候选[0] 应为 lv，实际 " + Arrays.toString(cands));
        assertEquals("lv lv", WakeWordPinyinUtils.toPinyin("绿绿"), "叠字守住取 [0]");
    }

    // ---------- D. 整词拒绝（防半截词/静默失效） ----------

    @Test
    public void testWholeWordRejections() {
        // 非 BMP 汉字（CJK Ext B+，U+20000+）：pinyin4j 只支持 BMP 单 char，
        // 静默丢弃会产出"半截但合法"的拼音（小禾𠮷 → xiao he），整词失败
        assertNull(WakeWordPinyinUtils.toPinyin("小禾𠮷"));
        assertNull(WakeWordPinyinUtils.toPinyin("小禾𠀀"));
        // BMP 表外字（U+3400 㐀）：转不出音节 → 整词失败
        assertNull(WakeWordPinyinUtils.toPinyin("小禾㐀"));
        // 汉字 + ASCII 字母混排：mn7_cn 无英文 token，整词拒绝（"小禾AI"→null 有意为之）
        assertNull(WakeWordPinyinUtils.toPinyin("小禾AI"));
    }

    @Test
    public void testWholeStringLengthRule() {
        // 整条拼音串 len>=2（判 join 后整串，非单 token）：
        assertNull(WakeWordPinyinUtils.toPinyin("哦"), "整串 len=1 → 不可用");
        assertNull(WakeWordPinyinUtils.toPinyin("啊"));
        // 注意别写成 null：「哦哦」→ "e e" 整串 len=3 合法
        assertEquals("e e", WakeWordPinyinUtils.toPinyin("哦哦"));
        assertEquals("a a", WakeWordPinyinUtils.toPinyin("啊啊"));
        // 无效输入
        assertNull(WakeWordPinyinUtils.toPinyin(""));
        assertNull(WakeWordPinyinUtils.toPinyin("   "));
        assertNull(WakeWordPinyinUtils.toPinyin(null));
    }

    @Test
    public void testDigitsConvertedToReading() {
        // MN7 中文模型对纯数字 token 整条拒绝，必须转中文读音
        assertEquals("xiao du er hao", WakeWordPinyinUtils.toPinyin("小度2号"));
    }

    // ---------- E. 反向契约（任何纯中文输出都成立） ----------

    @Test
    public void testOutputNeverContainsUnsafeChars() {
        // lue/nue 由别名表归一（jv/qv/xv 不归一，见 knownLimitation）；手填 ü 转 v
        String[] inputs = {"女绿旅", "略虐", "学月决缺", "句去虚", "你好小禾", "绿", "驴",
                "虐心", "区域", "嗯哼", "小度2号", "哦哦", "啊啊"};
        for (String in : inputs) {
            String out = WakeWordPinyinUtils.toPinyin(in);
            if (out == null) {
                continue;
            }
            for (char ch : out.toCharArray()) {
                assertFalse(ch == 'ü' || ch == ':' || Character.isDigit(ch),
                        in + " → " + out + " 含非法字符 '" + ch + "'");
            }
            assertFalse(out.contains("lue"), in + " → " + out + " 含 lue（别名表未归一）");
            assertFalse(out.contains("nue"), in + " → " + out + " 含 nue（别名表未归一）");
        }
    }

    // ---------- F. isFirmwareSafe 格式校验（产品口径 60 / 引擎 63） ----------

    @Test
    public void testIsFirmwareSafe() {
        assertTrue(WakeWordPinyinUtils.isFirmwareSafe("ni hao"));
        assertTrue(WakeWordPinyinUtils.isFirmwareSafe("nv lv lv"));
        assertFalse(WakeWordPinyinUtils.isFirmwareSafe("ni3 hao3"), "带调数字：NVS 自愈判过时格式删键");
        assertFalse(WakeWordPinyinUtils.isFirmwareSafe("ni|hao"), "NVS 列表分隔符");
        assertFalse(WakeWordPinyinUtils.isFirmwareSafe("Ni hao"), "大写");
        assertFalse(WakeWordPinyinUtils.isFirmwareSafe("lu:e4"), "WITH_V 退化（lu:e4）兜底");
        assertTrue(WakeWordPinyinUtils.isFirmwareSafe("a".repeat(60)), "60=产品上限，通过");
        assertFalse(WakeWordPinyinUtils.isFirmwareSafe("a".repeat(61)),
                "61~62 被产品侧提前拦住是预期（引擎硬上限 63），不是 bug");
    }

    @Test
    public void knownLimitation_handFilledAsciiPassthrough() {
        // 设计如此（design-as-is）：手填纯 ASCII 是多音字逃生通道，
        // token 级白名单未实现——"ok"/"hello"/"abc"/"jv" 会放行、固件收下但永不命中。
        // 若未来实现 405 音节白名单，这两条要同步改断言。
        assertTrue(WakeWordPinyinUtils.isFirmwareSafe("xiao he ok"), "手填拼音逃生通道放行");
        assertTrue(WakeWordPinyinUtils.isFirmwareSafe("jv"), "别名表只覆盖 lue/nue，jv 不归一");
    }

    // ---------- G. 成对下发（toFirmwarePairs） ----------

    @Test
    public void testToFirmwarePairs() {
        List<String[]> pairs = WakeWordPinyinUtils.toFirmwarePairs(
                Arrays.asList("你好小禾", "", "嗯", "小禾𠀀", "小度2号"));
        // ""（空输入）与小禾𠀀（非 BMP）拼音/display 一起被剔除 → 恰好 3 对
        assertEquals(3, pairs.size(), "实际 " + pairs.size());
        // 逐项同源断言（不能只断言数量，否则错位测不出来）
        assertEquals("ni hao xiao he", pairs.get(0)[0]);
        assertEquals("你好小禾", pairs.get(0)[1]);
        assertEquals("en", pairs.get(1)[0]);
        assertEquals("嗯", pairs.get(1)[1]);
        assertEquals("xiao du er hao", pairs.get(2)[0]);
        assertEquals("小度2号", pairs.get(2)[1]);
    }

    // ---------- H. 短语表前缀遮蔽防护（matchPhrase 按数组顺序首个 startsWith 命中） ----------

    @Test
    @SuppressWarnings("unchecked")
    public void testPhraseTableSelfConsistent() throws Exception {
        // 整表自洽（防"改一条碰坏另一条"）：遍历 PHRASE_OVERRIDES 全部条目，
        // 逐条断言 toPinyin(词) == 表内期望拼音。toPinyin 走短语命中 + 后续逐字，
        // 能同时验证级联（如「为什么要」= 3 字命中 + "要" 逐字）。
        Field f = WakeWordPinyinUtils.class.getDeclaredField("PHRASE_OVERRIDES");
        f.setAccessible(true);
        String[][] table = (String[][]) f.get(null);
        for (String[] e : table) {
            assertEquals(e[1], WakeWordPinyinUtils.toPinyin(e[0]), "短语表自洽: " + e[0]);
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    public void testPhraseTableNoPrefixShadowing() throws Exception {
        // 风险：若 2 字词插到构成前缀的 3 字词之前（如 "为什" 在 "为什么" 前），
        // 长词永久失效且无任何报错。当前基线 entries=32、shadow=0。
        Field f = WakeWordPinyinUtils.class.getDeclaredField("PHRASE_OVERRIDES");
        f.setAccessible(true);
        String[][] table = (String[][]) f.get(null);
        for (int i = 0; i < table.length; i++) {
            for (int j = 0; j < table.length; j++) {
                if (i != j && table[j][0].startsWith(table[i][0])) {
                    // 存在前缀对时，长词必须排在短词前面（j 为长词，要求 j < i）
                    assertTrue(j < i,
                            "短语表前缀遮蔽：" + table[i][0] + " 排在 " + table[j][0] + " 之前，长词会被截走");
                }
            }
        }
        assertEquals(32, table.length, "短语表条数变更时请复核本测试全部用例");
    }
}
