import java.util.Arrays;
import java.util.List;

import yuhe.common.utils.WakeWordPinyinUtils;

/**
 * 离线实跑驱动：证明「汉字→固件可用无调拼音」与「拼音/汉字成对」两段逻辑。
 * 不连接任何服务，不写任何文件，纯 stdout。
 */
public class PinyinDriver {

    public static void main(String[] args) {
        System.out.println("== toPinyin 单条 ==");
        for (String w : new String[]{"早上好", "你好小禾", "小方块", "为什么", "银行", "关灯", "小禾AI", "嗯"}) {
            System.out.println(w + " => " + String.valueOf(WakeWordPinyinUtils.toPinyin(w)));
        }

        System.out.println("\n== toFirmwarePairs 成对 ==");
        List<String[]> pairs = WakeWordPinyinUtils.toFirmwarePairs(Arrays.asList("早上好"));
        for (String[] p : pairs) {
            System.out.println("pinyin=[" + p[0] + "] display=[" + p[1] + "]");
        }

        System.out.println("\n== toFirmwarePairs 多词 ==");
        for (String[] p : WakeWordPinyinUtils.toFirmwarePairs(Arrays.asList("早上好", "关灯", "小方块"))) {
            System.out.println("pinyin=[" + p[0] + "] display=[" + p[1] + "]");
        }

        System.out.println("\n== 断言 ==");
        String zao = WakeWordPinyinUtils.toPinyin("早上好");
        check("早上好 -> zao shang hao", "zao shang hao".equals(zao));
        check("拼音纯 ASCII 小写无调", zao != null && zao.matches("[a-z ]+"));
        check("isFirmwareSafe(zao shang hao)", WakeWordPinyinUtils.isFirmwareSafe("zao shang hao"));
        String[][] one = WakeWordPinyinUtils.toFirmwarePairs(Arrays.asList("早上好")).toArray(new String[0][]);
        check("成对：pinyin/display 各 1 条且等长", one.length == 1 && one[0].length == 2);
        check("成对：display 保留汉字原文", one.length == 1 && "早上好".equals(one[0][1]));
        check("成对：pinyin 为 zao shang hao", one.length == 1 && "zao shang hao".equals(one[0][0]));
        check("多音词覆盖：为什么 -> wei shen me", "wei shen me".equals(WakeWordPinyinUtils.toPinyin("为什么")));
        check("多音词覆盖：银行 -> yin hang（非 yin xing）", "yin hang".equals(WakeWordPinyinUtils.toPinyin("银行")));
        check("别名：嗯 -> en（非 ng）", "en".equals(WakeWordPinyinUtils.toPinyin("嗯")));
        check("混排拒绝：小禾AI -> null", WakeWordPinyinUtils.toPinyin("小禾AI") == null);
        System.out.println("\nRESULT=" + (failed == 0 ? "ALL_PASS" : "FAILED:" + failed));
        if (failed != 0) {
            System.exit(1);
        }
    }

    private static int failed = 0;

    private static void check(String name, boolean ok) {
        System.out.println((ok ? "  PASS  " : "  FAIL  ") + name);
        if (!ok) {
            failed++;
        }
    }
}
