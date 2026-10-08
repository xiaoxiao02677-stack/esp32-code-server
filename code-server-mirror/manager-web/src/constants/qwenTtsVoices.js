/**
 * 千问 TTS 平台音色内置映射
 *
 * 平台未提供音色列表查询 API，前端按官方文档内置各模型支持的音色：
 * - qwen3-tts-flash：48 个音色（含普通话、国际、方言三组）
 * - qwen3-tts-instruct-flash：前 24 个普通话音色（Cherry → Stella 片段，剔除国际音色）
 * - qwen-tts：4 个基础音色；qwen-tts-latest 追加 3 个方言音色
 * - qwen-audio 系列：另一套龙系列音色，plus 旗舰追加 2 个
 */

const GROUP_MANDARIN = 'mandarin';
const GROUP_INTERNATIONAL = 'international';
const GROUP_DIALECT = 'dialect';

// qwen3-tts-flash 全量 48 音色（顺序与官方文档一致）
export const QWEN_TTS_FLASH_VOICES = [
  { voice: 'Cherry', label: 'Cherry（芊悦）', group: GROUP_MANDARIN },
  { voice: 'Serena', label: 'Serena（苏瑶）', group: GROUP_MANDARIN },
  { voice: 'Ethan', label: 'Ethan（晨煦）', group: GROUP_MANDARIN },
  { voice: 'Chelsie', label: 'Chelsie（千雪）', group: GROUP_MANDARIN },
  { voice: 'Momo', label: 'Momo（茉兔）', group: GROUP_MANDARIN },
  { voice: 'Vivian', label: 'Vivian（十三）', group: GROUP_MANDARIN },
  { voice: 'Moon', label: 'Moon（月白）', group: GROUP_MANDARIN },
  { voice: 'Maia', label: 'Maia（四月）', group: GROUP_MANDARIN },
  { voice: 'Kai', label: 'Kai（凯）', group: GROUP_MANDARIN },
  { voice: 'Nofish', label: 'Nofish（不吃鱼）', group: GROUP_MANDARIN },
  { voice: 'Bella', label: 'Bella（萌宝）', group: GROUP_MANDARIN },
  { voice: 'Jennifer', label: 'Jennifer（詹妮弗）', group: GROUP_INTERNATIONAL },
  { voice: 'Ryan', label: 'Ryan（甜茶）', group: GROUP_INTERNATIONAL },
  { voice: 'Katerina', label: 'Katerina（卡捷琳娜）', group: GROUP_INTERNATIONAL },
  { voice: 'Aiden', label: 'Aiden（艾登）', group: GROUP_INTERNATIONAL },
  { voice: 'Eldric Sage', label: 'Eldric Sage（沧明子）', group: GROUP_MANDARIN },
  { voice: 'Mia', label: 'Mia（乖小妹）', group: GROUP_MANDARIN },
  { voice: 'Mochi', label: 'Mochi（沙小弥）', group: GROUP_MANDARIN },
  { voice: 'Bellona', label: 'Bellona（燕铮莺）', group: GROUP_MANDARIN },
  { voice: 'Vincent', label: 'Vincent（田叔）', group: GROUP_MANDARIN },
  { voice: 'Bunny', label: 'Bunny（萌小姬）', group: GROUP_MANDARIN },
  { voice: 'Neil', label: 'Neil（阿闻）', group: GROUP_MANDARIN },
  { voice: 'Elias', label: 'Elias（墨讲师）', group: GROUP_MANDARIN },
  { voice: 'Arthur', label: 'Arthur（徐大爷）', group: GROUP_MANDARIN },
  { voice: 'Nini', label: 'Nini（邻家妹妹）', group: GROUP_MANDARIN },
  { voice: 'Seren', label: 'Seren（小婉）', group: GROUP_MANDARIN },
  { voice: 'Pip', label: 'Pip（顽屁小孩）', group: GROUP_MANDARIN },
  { voice: 'Stella', label: 'Stella（少女阿月）', group: GROUP_MANDARIN },
  { voice: 'Bodega', label: 'Bodega', group: GROUP_INTERNATIONAL },
  { voice: 'Sonrisa', label: 'Sonrisa', group: GROUP_INTERNATIONAL },
  { voice: 'Alek', label: 'Alek', group: GROUP_INTERNATIONAL },
  { voice: 'Dolce', label: 'Dolce', group: GROUP_INTERNATIONAL },
  { voice: 'Sohee', label: 'Sohee', group: GROUP_INTERNATIONAL },
  { voice: 'Ono Anna', label: 'Ono Anna', group: GROUP_INTERNATIONAL },
  { voice: 'Lenn', label: 'Lenn', group: GROUP_INTERNATIONAL },
  { voice: 'Emilien', label: 'Emilien', group: GROUP_INTERNATIONAL },
  { voice: 'Andre', label: 'Andre', group: GROUP_INTERNATIONAL },
  { voice: 'Radio Gol', label: 'Radio Gol', group: GROUP_INTERNATIONAL },
  { voice: 'Jada', label: 'Jada（上海-阿珍）', group: GROUP_DIALECT },
  { voice: 'Dylan', label: 'Dylan（北京-晓东）', group: GROUP_DIALECT },
  { voice: 'Li', label: 'Li', group: GROUP_DIALECT },
  { voice: 'Marcus', label: 'Marcus', group: GROUP_DIALECT },
  { voice: 'Roy', label: 'Roy', group: GROUP_DIALECT },
  { voice: 'Peter', label: 'Peter', group: GROUP_DIALECT },
  { voice: 'Sunny', label: 'Sunny（四川-晴儿）', group: GROUP_DIALECT },
  { voice: 'Eric', label: 'Eric', group: GROUP_DIALECT },
  { voice: 'Rocky', label: 'Rocky', group: GROUP_DIALECT },
  { voice: 'Kiki', label: 'Kiki', group: GROUP_DIALECT }
];

// qwen3-tts-instruct-flash：Cherry → Stella 片段中的普通话音色（24 个）
export const QWEN_TTS_INSTRUCT_VOICES = QWEN_TTS_FLASH_VOICES
  .slice(0, 28)
  .filter(item => item.group === GROUP_MANDARIN);

// qwen-tts 基础音色（qwen-tts / qwen-tts-2025-04-10 / qwen-tts-2025-05-22）
export const QWEN_TTS_BASIC_VOICE_NAMES = ['Cherry', 'Serena', 'Ethan', 'Chelsie'];

// qwen-tts-latest 在基础音色之上追加的方言音色
export const QWEN_TTS_LATEST_EXTRA_VOICE_NAMES = ['Jada', 'Dylan', 'Sunny'];

// qwen-audio 系列基础音色（12 个）
export const QWEN_AUDIO_TTS_VOICE_NAMES = [
  'longanhuan_v3.6',
  'longanfengyue',
  'longanyuanfei',
  'longanlingxi',
  'longanxiaoxin',
  'longjielidou_v3.6',
  'longpaopao_v3.6',
  'longhuohuo_v3.6',
  'longchuanshu_v3.6',
  'loongmary',
  'loongeva_v3.6',
  'loongjohn'
];

// qwen-audio plus 旗舰追加音色（2 个）
export const QWEN_AUDIO_TTS_PLUS_EXTRA_VOICE_NAMES = ['longanlingxin', 'longanlufeng'];

function findFlashVoice(voice) {
  return QWEN_TTS_FLASH_VOICES.find(item => item.voice === voice);
}

function pickVoices(names) {
  return names
    .map(name => findFlashVoice(name) || { voice: name, label: name, group: GROUP_DIALECT })
    .map(item => ({ ...item }));
}

/**
 * 根据模型 ID 返回该模型支持的音色选项列表
 * @param {string} modelId 千问 TTS 模型 ID
 * @returns {Array<{voice: string, label: string, group: string}>|null}
 *          模型 ID 不在内置映射时返回 null（下拉退化为 allow-create 手填）
 */
export function getQwenTtsVoiceOptions(modelId) {
  if (!modelId || typeof modelId !== 'string') {
    return null;
  }
  const id = modelId.trim().toLowerCase();
  if (!id) {
    return null;
  }

  // qwen-audio 系列（另一套龙系列音色）
  if (id.includes('audio')) {
    const options = QWEN_AUDIO_TTS_VOICE_NAMES.map(name => ({
      voice: name,
      label: name,
      group: GROUP_MANDARIN
    }));
    if (id.includes('plus') || id.includes('flagship')) {
      return options.concat(QWEN_AUDIO_TTS_PLUS_EXTRA_VOICE_NAMES.map(name => ({
        voice: name,
        label: name,
        group: GROUP_INTERNATIONAL
      })));
    }
    return options;
  }

  // qwen3-tts-instruct-flash（含 realtime / 日期版本）
  if (id.includes('instruct')) {
    return QWEN_TTS_INSTRUCT_VOICES.map(item => ({ ...item }));
  }

  // qwen-tts 基础版（仅 4 音色）
  if (/^qwen-tts(-\d{4}-\d{2}-\d{2})?$/.test(id)) {
    return pickVoices(QWEN_TTS_BASIC_VOICE_NAMES);
  }

  // qwen-tts-latest（4 + 3 方言）
  if (id === 'qwen-tts-latest') {
    return pickVoices(QWEN_TTS_BASIC_VOICE_NAMES.concat(QWEN_TTS_LATEST_EXTRA_VOICE_NAMES));
  }

  // qwen3-tts-flash 及其余千问 TTS 模型（含 realtime / 日期版本）→ 全量 48
  if (id.includes('qwen')) {
    return QWEN_TTS_FLASH_VOICES.map(item => ({ ...item }));
  }

  return null;
}
