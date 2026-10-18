package xiaozhi.common.utils;

import java.util.ArrayList;
import java.util.List;

import net.sourceforge.pinyin4j.PinyinHelper;
import net.sourceforge.pinyin4j.format.HanyuPinyinCaseType;
import net.sourceforge.pinyin4j.format.HanyuPinyinOutputFormat;
import net.sourceforge.pinyin4j.format.HanyuPinyinToneType;
import net.sourceforge.pinyin4j.format.HanyuPinyinVCharType;

/**
 * 唤醒词汉字→无调拼音（ESP32 固件 MultiNet 命令词格式）。
 *
 * <p>输出约定：<b>无调、小写、空格分隔、纯 ASCII</b>，如 "你好小禾" → "ni hao xiao he"。
 * 固件按字节处理非 ASCII 字符、NVS 自愈逻辑会把形如 "ni3" 的带调数字判为过时格式丢弃，
 * 所以这里绝不产出声调符号或数字调。
 *
 * <p>为什么不用固件内置字表：固件为避免引入完整拼音库，只收录约 100 个常见字，
 * 表外字（如"鬼"）整词被丢弃。服务端转好拼音下发后（{@code wake_word} 传拼音 +
 * {@code wake_word_display} 传汉字），任意中文唤醒词都能用。
 *
 * <p>多音字注意：pinyin4j 是单字映射，"银行"会被转成 "yin xing"。若唤醒词含多音字，
 * 用户可直接输入拼音（纯 ASCII 会原样保留），这是官方逃生通道。
 */
public final class WakeWordPinyinUtils {

    /**
     * 拼音单条长度上限。取 60：esp-sr 引擎硬上限 `ESP_MN_MAX_PHRASE_LEN=63`
     * （实际可用 62），留余量。也不要卡 32：最坏音节 6 字母（zhuang），
     * N 音节长 7N-1，5 音节最坏 34 > 32，会被静默丢弃，
     * 用户看到的是"保存成功但设备仍是旧词"，极难排查。
     */
    public static final int MAX_PINYIN_LENGTH = 60;
    /** 展示文本（汉字）单条上限，与设备侧 display 约束一致 */
    public static final int MAX_DISPLAY_LENGTH = 32;
    public static final int MAX_WORD_COUNT = 5;

    /**
     * 多音字短语覆盖表（<b>必须按长度降序</b>，匹配是顺序遍历 + startsWith 首个命中即返回）。
     * pinyin4j 是单字映射，"音乐"会转成 yin le、"银行"转成 yin xing，唤醒词会被念错。
     * 这里覆盖唤醒词场景的常见多音词；表外的多音字仍可能不准，用户可直接输入拼音
     * （纯 ASCII 原样保留）——这是官方逃生通道。
     */
    private static final String[][] PHRASE_OVERRIDES = {
            // ---- 3 字（必须排在 2 字前面，否则"为什么"会被"什么"截走）----
            {"为什么", "wei shen me"},
            // ---- 2 字 ----
            {"音乐", "yin yue"}, {"银行", "yin hang"}, {"重庆", "chong qing"},
            {"长大", "zhang da"}, {"觉得", "jue de"}, {"睡觉", "shui jiao"},
            {"重要", "zhong yao"}, {"重新", "chong xin"}, {"快乐", "kuai le"},
            {"行走", "xing zou"}, {"了解", "liao jie"}, {"着急", "zhao ji"},
            {"得到", "de dao"}, {"空中", "kong zhong"}, {"还有", "hai you"},
            {"首都", "shou du"}, {"东西", "dong xi"}, {"地方", "di fang"},
            {"什么", "shen me"}, {"一个", "yi ge"}, {"这个", "zhe ge"},
            {"那个", "na ge"}, {"不是", "bu shi"}, {"没有", "mei you"},
            // 实测 pinyin4j 会转错的日常词/地名（不补则唤醒词静默不命中）
            {"长江", "chang jiang"}, {"归还", "gui huan"}, {"厦门", "xia men"},
            {"调解", "tiao jie"}, {"番禺", "pan yu"}, {"六安", "lu an"},
            {"单县", "shan xian"},
    };

    /** 数字→中文读法：MN7 中文模型对纯数字 token（"2"）会整条拒绝，必须转成读音 */
    private static final String[] DIGIT_PINYIN = {
            "ling", "yi", "er", "san", "si", "wu", "liu", "qi", "ba", "jiu"
    };

    /**
     * 音节别名：pinyin4j 产出但引擎词表不认的音节 → 等价可用音节。
     *
     * <p>「嗯」是高频唤醒词用字：pinyin4j 给 {@code ng}（mn7_cn 无此 token，
     * 整条会被拒），而旧固件内置字表映射成 {@code en}（可用）。
     * 不做这个别名就是一次功能回退——用户从"能用"变成"配了没反应"。
     * {@code en} 与「嗯」的鼻音读法一致，用户念"恩"即命中。
     *
     * <p>其余生僻字仍走拒绝路径（见 {@link #NON_VOCAB_SYLLABLES}）：
     * 没有旧行为可兼容，静默失效比明确拒绝更糟。
     */
    private static final java.util.Map<String, String> SYLLABLE_ALIASES =
            java.util.Map.of(
                    "ng", "en",     // 「嗯」→ en
                    "lue", "lve",   // 「略」手填 lue → 字表形式 lve
                    "nue", "nve");  // 「虐」手填 nue → 字表形式 nve

    /**
     * pinyin4j 能产出、mn7_cn 词表里没有、且无合适别名的音节（穷举得到的闭集）。
     *
     * <p>来源：对 pinyin4j 全量音节与「mn7_cn 408 个拼音 token」比对，只有
     * m / ng / yiao 三个出表；ng 已由 {@link #SYLLABLE_ALIASES} 别名成 en。
     * 下发它们固件不报错、只是永远命中不了，用户侧表现为"保存成功但喊破喉咙也不应"，
     * 是最难排查的一类失效——所以在下发前就拒掉这条词。
     *
     * <p>注意：这拦的是<b>汉字转换路径</b>。用户手填纯 ASCII 拼音的逃生通道
     * （见 toPinyin 注释）不走此校验，"ok" 这类仍会被放行——那需要 405 音节白名单
     * 才能拦，而白名单会随模型换代过期，收益不抵维护成本，改由前端提示兜住。
     */
    private static final java.util.Set<String> NON_VOCAB_SYLLABLES =
            java.util.Set.of("m", "yiao");

    private static final HanyuPinyinOutputFormat FORMAT = new HanyuPinyinOutputFormat();

    static {
        FORMAT.setToneType(HanyuPinyinToneType.WITHOUT_TONE);
        FORMAT.setCaseType(HanyuPinyinCaseType.LOWERCASE);
        // ü → v：与固件字表一致（{"女","nv"}），避免非 ASCII 的 ü 被丢弃
        FORMAT.setVCharType(HanyuPinyinVCharType.WITH_V);
    }

    private WakeWordPinyinUtils() {
    }

    /**
     * 汉字转无调拼音；已是拼音/英文/数字的部分原样保留。
     *
     * <p><b>失败返回 {@code null}，绝不返回空串</b>。调用方必须判 null 并跳过该词：
     * 把空串当合法值下发，固件会收到空命令词条（比不下发更糟）。
     * "失败"包含：输入空白、含表外汉字（无法转出音节）、结果没有任何 token。
     */
    public static String toPinyin(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        // 汉字 + ASCII 字母混排（"小禾AI"）：mn7_cn 词表没有任何英文 token，
        // 字母段要么被静默丢弃要么整条被拒，而"xiao he ai"里的 ai 恰好是合法音节，
        // 会保存成功但只有念"爱"才可能命中——语义完全跑偏。整词拒绝，让用户换成纯中文。
        if (containsHanzi(text) && hasAsciiLetter(text)) {
            return null;
        }
        List<String> tokens = new ArrayList<>(text.length());
        StringBuilder asciiRun = new StringBuilder(8);
        int i = 0;
        while (i < text.length()) {
            // 1) 多音字短语优先：最长匹配，命中则整段替换
            String matchedPinyin = matchPhrase(text, i);
            if (matchedPinyin != null) {
                flushAsciiRun(asciiRun, tokens);
                for (String token : matchedPinyin.split(" ")) {
                    if (!token.isEmpty()) {
                        tokens.add(token);
                    }
                }
                i += phraseLength(text, i);
                continue;
            }
            int codePoint = text.codePointAt(i);
            int charCount = Character.charCount(codePoint);
            i += charCount;
            // 2) 数字转中文读法（MN7 中文模型不认纯数字 token）
            if (codePoint >= '0' && codePoint <= '9') {
                flushAsciiRun(asciiRun, tokens);
                tokens.add(DIGIT_PINYIN[codePoint - '0']);
            } else if (Character.isIdeographic(codePoint)) {
                flushAsciiRun(asciiRun, tokens);
                // 扩展 B 及以后（CJK Ext B/C/D，U+20000+）：pinyin4j 只支持 BMP 单 char，
                // 转不出音节。若在这里静默丢弃，会产出"半截但完全合法"的拼音
                //（"小禾𠮷" → "xiao he"）——固件照单全收，用户设了 4 个字却只认 2 个，
                // 且日志无任何异常，是最难排查的一类失效。整词失败，与表外汉字同语义。
                if (codePoint > 0xFFFF) {
                    return null;
                }
                // 汉字逐字转；表外字整词失败（跳过会产出半截词，用户以为生效但念不全）
                String syllable = toSyllable((char) codePoint);
                if (syllable.isEmpty()) {
                    return null;
                }
                tokens.add(syllable);
            } else if (codePoint == 'ü' || codePoint == 'Ü') {
                // 手填拼音里的 ü：非 ASCII，会被下面"标点一律丢弃"吃掉（"nü" → "n"）。
                // 固件字表用 v 表示 ü（{"女","nv"}），这里同样转 v
                asciiRun.append('v');
            } else if (isAsciiAlnum(codePoint)) {
                // 英文/字母串保留：这是"用户直接手填拼音"的官方逃生通道
                //（多音字不准时用它纠正，如 "yin hang"）。
                // 代价：手填 "ok"/"hello" 这类非拼音串也会被放行，固件收下但永远命中不了；
                // 拦住它需要 405 音节白名单，而白名单随模型换代过期，改由前端提示兜住。
                asciiRun.append((char) codePoint);
            } else {
                // 空格/标点/全角符号/emoji 一律丢弃（固件也会丢弃，留着只会污染命令词）
                flushAsciiRun(asciiRun, tokens);
            }
        }
        flushAsciiRun(asciiRun, tokens);
        if (tokens.isEmpty()) {
            return null;
        }
        // 4) 出表音节整词失败：与"表外汉字整词失败"同语义，只拒这一条、其它词不受影响。
        //    放在 join 之前而非 isFirmwareSafe，是为了让手填纯 ASCII 的逃生通道不受影响。
        for (String token : tokens) {
            if (NON_VOCAB_SYLLABLES.contains(token)) {
                return null;
            }
        }
        String joined = String.join(" ", tokens);
        // 5) 整串长度 < 2 直接失败（「哦」→ e、「啊」→ a）。
        //    ★ 必须判整串、绝不能逐 token 判：固件看的是整条命令串的 strlen，
        //    e/o/a 作为单个 token 在词表里完全合法，叠字「哦哦」→ "e e"（len=3）
        //    是能正常唤醒的。逐 token 要求 ≥2 会误杀所有叠字唤醒词。
        //    这里再判一次而不只依赖 isFirmwareSafe：toPinyinList 等调用方不走那道校验。
        if (joined.length() < 2) {
            return null;
        }
        return joined;
    }

    /** 是否含 ASCII 字母（用于拦截汉字与英文字母混排） */
    private static boolean hasAsciiLetter(String text) {
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z')) {
                return true;
            }
        }
        return false;
    }

    /** 在 offset 处匹配多音字短语，返回拼音串（空格分隔）或 null */
    private static String matchPhrase(String text, int offset) {
        for (String[] entry : PHRASE_OVERRIDES) {
            if (text.startsWith(entry[0], offset)) {
                return entry[1];
            }
        }
        return null;
    }

    /** 返回 offset 处命中的短语长度（字符数） */
    private static int phraseLength(String text, int offset) {
        for (String[] entry : PHRASE_OVERRIDES) {
            if (text.startsWith(entry[0], offset)) {
                return entry[0].length();
            }
        }
        return 0;
    }

    /**
     * 批量转换；转换失败（空结果）的词被跳过。
     *
     * <p>调用方应校验返回数量与入参是否一致：少了说明该词无法转拼音，
     * 不能静默下发（会让设备丢掉这个词）。
     */
    public static List<String> toPinyinList(List<String> words) {
        List<String> result = new ArrayList<>();
        if (words == null) {
            return result;
        }
        for (String word : words) {
            String pinyin = toPinyin(word);
            if (pinyin != null) {
                result.add(pinyin);
            }
        }
        return result;
    }

    /**
     * 成对构建下发数据：{拼音, 展示原文}。无法转出固件可用拼音的词被跳过
     * （调用方应校验返回是否为空，全空则保留设备原配置，不要下发空表）。
     * <p>展示原文里的 '|' 换成空格：NVS 用 '|' 作列表分隔符，混进来会把一条拆成两条。
     */
    public static List<String[]> toFirmwarePairs(List<String> words) {
        List<String[]> pairs = new ArrayList<>();
        if (words == null) {
            return pairs;
        }
        for (String word : words) {
            if (word == null || word.isBlank()) {
                continue;
            }
            String display = word.trim().replace('|', ' ');
            String pinyin = toPinyin(display);
            if (pinyin == null || !isFirmwareSafe(pinyin)) {
                continue;
            }
            pairs.add(new String[]{pinyin, display});
        }
        return pairs;
    }

    /**
     * 下发前最终校验（固件 + 引擎契约）：纯 ASCII、仅 [a-z ]、1~60 字符、无连续空格。
     *
     * <p>数字也拒绝：mn7_cn 词表的 408 个 token 全是拼音音节，没有任何数字；
     * 带声调数字（"ni3"）更会被固件 NVS 自愈逻辑判为过时格式直接删键。
     * 当前 toPinyin 已把数字转成中文读音，正常不会产出数字——这条是防回归的兜底。
     *
     * <p>不通过就不该下发——固件会静默丢弃或整条拒绝，用户无从得知。
     */
    public static boolean isFirmwareSafe(String pinyin) {
        if (pinyin == null || pinyin.isEmpty() || pinyin.length() > MAX_PINYIN_LENGTH) {
            return false;
        }
        // 引擎要求 2 ≤ len（单字符音节 a/o/e 会被 esp_mn 单条拒绝，见
        // esp_mn_speech_commands.c:108-121）。单字唤醒词（「啊」「哦」）因此不可用：
        // 让它在保存时明确失败，好过"保存成功但永远唤不醒"
        if (pinyin.length() < 2) {
            return false;
        }
        if (!pinyin.equals(pinyin.trim()) || pinyin.contains("  ")) {
            return false;
        }
        for (int i = 0; i < pinyin.length(); i++) {
            char ch = pinyin.charAt(i);
            if (!((ch >= 'a' && ch <= 'z') || ch == ' ')) {
                return false;
            }
        }
        return true;
    }

    /**
     * 清洗已有拼音串：只保留 [a-z0-9 ]，折叠空白、去首尾、转小写。
     * 用于下发前兜底（库里可能存了大写、带 '|' 的脏值）。
     */
    public static String normalizePinyin(String raw) {
        if (raw == null || raw.isBlank()) {
            return "";
        }
        StringBuilder sb = new StringBuilder(raw.length());
        boolean lastSpace = true;
        for (int i = 0; i < raw.length(); i++) {
            char ch = raw.charAt(i);
            if (ch == ' ' || ch == '\t' || ch == '|') {
                if (sb.length() > 0 && !lastSpace) {
                    sb.append(' ');
                    lastSpace = true;
                }
                continue;
            }
            if (ch < 0x20 || ch == 0x7F) {
                continue;
            }
            if (ch >= 'a' && ch <= 'z') {
                sb.append(ch);
                lastSpace = false;
            } else if (ch >= 'A' && ch <= 'Z') {
                sb.append((char) (ch - 'A' + 'a'));
                lastSpace = false;
            }
            // 数字直接丢弃：库里可能存着 "ni3 hao3" 这种带声调数字的过时格式，
            // 固件 NVS 自愈逻辑会把整条判为过时并删键。丢弃数字即降级为合法无调拼音。
            // 其他字符（声调符号、中文标点）同样丢弃
        }
        if (sb.length() > 0 && sb.charAt(sb.length() - 1) == ' ') {
            sb.setLength(sb.length() - 1);
        }
        return sb.toString();
    }

    /** 是否为合法拼音串（非空、仅 [a-z0-9 ]） */
    public static boolean isPinyinOnly(String text) {
        if (text == null || text.isBlank()) {
            return false;
        }
        String normalized = normalizePinyin(text);
        return !normalized.isEmpty() && normalized.length() == text.trim().replaceAll("\\s+", " ").length();
    }

    /** 是否含汉字（含汉字说明是旧数据/未转换的汉字唤醒词） */
    public static boolean containsHanzi(String text) {
        if (text == null) {
            return false;
        }
        for (int i = 0; i < text.length(); ) {
            int codePoint = text.codePointAt(i);
            i += Character.charCount(codePoint);
            if (codePoint <= 0xFFFF && Character.isIdeographic(codePoint)) {
                return true;
            }
        }
        return false;
    }

    /** 单字转无调拼音音节；表外字返回空串 */
    private static String toSyllable(char c) {
        try {
            String[] candidates = PinyinHelper.toHanyuPinyinStringArray(c, FORMAT);
            if (candidates == null || candidates.length == 0) {
                return "";
            }
            String syllable = candidates[0];
            StringBuilder sb = new StringBuilder(syllable.length());
            for (int i = 0; i < syllable.length(); i++) {
                char ch = syllable.charAt(i);
                // ü → v：FORMAT 已设 WITH_V，正常不会走到这里；
                // 但漏掉这个字符会让「绿」变成 "l"（不是 "lv"），产出非法命令词，故兜一道
                if (ch == 'ü' || ch == 'Ü') {
                    sb.append('v');
                    continue;
                }
                if (ch < 0x80 && Character.isLetterOrDigit(ch)) {
                    sb.append(Character.toLowerCase(ch));
                }
            }
            // 音节别名：「嗯」→ ng（引擎词表无此 token）→ en（旧固件内置字表的行为，可用）
            String result = sb.toString();
            return SYLLABLE_ALIASES.getOrDefault(result, result);
        } catch (Exception e) {
            return "";
        }
    }

    private static void flushAsciiRun(StringBuilder asciiRun, List<String> tokens) {
        if (asciiRun.length() > 0) {
            String token = asciiRun.toString().toLowerCase();
            asciiRun.setLength(0);
            // 手填拼音同样套别名：固件字表用 v 表示 ü，用户手填 "lue"/"nue"
            //（或写了 "lüe" 被上面的 ü 分支归一成 lve）都得落到字表形式，否则是出表音节
            tokens.add(SYLLABLE_ALIASES.getOrDefault(token, token));
        }
    }

    private static boolean isAsciiAlnum(int codePoint) {
        return (codePoint >= '0' && codePoint <= '9')
                || (codePoint >= 'a' && codePoint <= 'z')
                || (codePoint >= 'A' && codePoint <= 'Z');
    }
}
