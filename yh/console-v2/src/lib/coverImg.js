/**
 * 商品封面图 URL 判定与归一化。
 *
 * cover 字段存的可能是：emoji/文字、外站图片 URL、本站封面 URL（相对或绝对）。
 * 本站封面（/goods/cover/{md5}.ext，经 /yuhe/ 反代）如果是带 host 的绝对地址
 * （早期版本上传返回 http://sandyun.top:8144/...），在 https 页面会被浏览器
 * 混合内容策略拦截——统一剥掉 host 转成同源相对路径再渲染。
 */

/** 是否为图片 URL（http(s) / data: / 站内相对路径） */
export function isImgCover(v) {
  const s = String(v || '').trim()
  return !!s && (/^https?:\/\//i.test(s) || s.startsWith('data:image/') || s.startsWith('/'))
}

/** 归一化为可直接给 <img :src> 的地址：本站封面绝对 URL → 同源相对路径 */
export function coverSrc(v) {
  const s = String(v || '').trim()
  if (/^https?:\/\//i.test(s)) {
    try {
      const u = new URL(s)
      // 只归一化本站封面路径；外站图片按原 URL 加载（https 外链不受混合内容限制）
      const m = u.pathname.match(/(\/yuhe)?\/goods\/cover\/[0-9a-f]{32}\.(png|jpe?g|webp|gif)$/i)
      if (m) return m[0]
    } catch { /* 非法 URL 原样返回 */ }
  }
  return s
}
