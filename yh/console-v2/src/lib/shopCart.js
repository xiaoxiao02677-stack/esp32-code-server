// 独立商店（/shop）游客购物车：localStorage 持久化，无登录态。
// 结构：[{ goodsId, name, cover, price, stock, category, qty, checked }]（快照商品信息，避免每次拉 on-sale 比对）
const KEY = 'guest_cart_v1'

export function loadCart() {
  try {
    const raw = localStorage.getItem(KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function saveCart(items) {
  localStorage.setItem(KEY, JSON.stringify(items))
}

/** 加购/累加数量（同商品合并；上限 99） */
export function addToCart(goods, qty = 1) {
  const items = loadCart()
  const id = String(goods.id)
  const hit = items.find((it) => String(it.goodsId) === id)
  if (hit) {
    hit.qty = Math.min(99, Number(hit.qty) + Number(qty))
  } else {
    items.unshift({
      goodsId: id,
      name: goods.name,
      cover: goods.cover || '🛍️',
      price: goods.price,
      stock: goods.stock,
      category: goods.category || '通用',
      qty: Math.min(99, Math.max(1, Number(qty))),
      checked: 1
    })
  }
  saveCart(items)
  return items
}

/** 数量步进（减到 0 移除）；返回新数组 */
export function changeQty(goodsId, delta) {
  let items = loadCart()
  const id = String(goodsId)
  const hit = items.find((it) => String(it.goodsId) === id)
  if (!hit) return items
  hit.qty = Number(hit.qty) + Number(delta)
  if (hit.qty < 1) {
    items = items.filter((it) => String(it.goodsId) !== id)
  } else if (hit.qty > 99) {
    hit.qty = 99
  }
  saveCart(items)
  return items
}

export function setQty(goodsId, qty) {
  const items = loadCart()
  const hit = items.find((it) => String(it.goodsId) === String(goodsId))
  if (!hit) return items
  const q = Number(qty)
  hit.qty = Number.isFinite(q) ? Math.min(99, Math.max(1, q)) : 1
  saveCart(items)
  return items
}

export function toggleChecked(goodsId, checked) {
  const items = loadCart()
  const hit = items.find((it) => String(it.goodsId) === String(goodsId))
  if (hit) {
    hit.checked = checked ? 1 : 0
    saveCart(items)
  }
  return items
}

export function removeItem(goodsId) {
  const items = loadCart().filter((it) => String(it.goodsId) !== String(goodsId))
  saveCart(items)
  return items
}

/** 清空已勾选行（下单成功后调用）；返回新数组 */
export function clearChecked() {
  const items = loadCart().filter((it) => String(it.checked) !== '1' && it.checked !== 1)
  saveCart(items)
  return items
}

export function cartCount() {
  return loadCart().reduce((s, it) => s + Number(it.qty || 0), 0)
}
