package yuhe.modules.order.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import yuhe.common.page.PageData;
import yuhe.modules.order.controller.CartMapper;
import yuhe.modules.order.controller.GoodsMapper;
import yuhe.modules.order.dao.OrderMapper;

/**
 * 电商小店业务：商品（管理端 CRUD + 顾客端浏览）+ 购物车 + 购物车下单（写 order_table，
 * 管理端 Orders.vue 零改动即可发货）。
 */
@Service
public class OrderShopService {

    private final GoodsMapper goodsMapper;
    private final CartMapper cartMapper;
    private final OrderMapper orderMapper;

    public OrderShopService(GoodsMapper goodsMapper, CartMapper cartMapper, OrderMapper orderMapper) {
        this.goodsMapper = goodsMapper;
        this.cartMapper = cartMapper;
        this.orderMapper = orderMapper;
    }

    // ==================== 商品：管理端 ====================

    public PageData<Map<String, Object>> goodsPage(int page, int limit, String keyword, String category, Integer status) {
        int offset = (Math.max(page, 1) - 1) * Math.max(limit, 1);
        List<Map<String, Object>> list = goodsMapper.selectList(keyword, category, status, offset, limit);
        int total = goodsMapper.selectCount(keyword, category, status);
        return new PageData<>(list, total);
    }

    public Map<String, Object> goodsInfo(Long id) {
        return goodsMapper.getById(id);
    }

    public Long goodsCreate(Map<String, Object> body) {
        if (body == null) {
            throw new IllegalArgumentException("商品信息不能为空");
        }
        normalize(body);
        goodsMapper.insert(body);
        Object id = body.get("id");
        return id == null ? null : Long.valueOf(String.valueOf(id));
    }

    public void goodsUpdate(Long id, Map<String, Object> body) {
        if (body == null || id == null) {
            throw new IllegalArgumentException("商品ID不能为空");
        }
        normalize(body);
        body.put("id", id);
        goodsMapper.update(body);
    }

    public void goodsDelete(Long id) {
        goodsMapper.delete(id);
    }

    public List<Map<String, Object>> goodsExport() {
        return goodsMapper.selectList(null, null, null, 0, 10000);
    }

    /** 上下架开关：PUT 语义复用 update */
    public void goodsToggle(Long id, Integer status) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("id", id);
        p.put("status", status == null ? 1 : status);
        goodsMapper.update(p);
    }

    private void normalize(Map<String, Object> body) {
        body.computeIfAbsent("status", k -> 1);
        body.computeIfAbsent("sort", k -> 0);
        Object price = body.get("price");
        if (price != null && !(price instanceof Number)) {
            body.put("price", new BigDecimal(String.valueOf(price)));
        }
    }

    // ==================== 商品：顾客端 ====================

    public List<Map<String, Object>> goodsOnSale() {
        return goodsMapper.selectOnSale();
    }

    public List<String> goodsCategories() {
        return goodsMapper.selectCategories();
    }

    // ==================== 购物车 ====================

    public List<Map<String, Object>> cartList(Long userId) {
        return cartMapper.selectWithGoods(userId);
    }

    public int cartCount(Long userId) {
        return cartMapper.selectWithGoods(userId).size();
    }

    @Transactional(rollbackFor = Exception.class)
    public void cartAdd(Long userId, Long goodsId, int qty) {
        if (goodsId == null) {
            throw new IllegalArgumentException("商品ID不能为空");
        }
        if (qty < 1) {
            qty = 1;
        }
        Map<String, Object> row = cartMapper.findRow(userId, goodsId);
        if (row != null) {
            // 已有同商品行：数量累加（上限 999，防恶意请求撑爆）
            Object oldQty = row.get("qty");
            int cur = oldQty == null ? 0 : Integer.parseInt(String.valueOf(oldQty));
            cartMapper.setQty(Long.valueOf(String.valueOf(row.get("id"))), Math.min(cur + qty, 999));
        } else {
            cartMapper.insert(userId, goodsId, qty);
        }
    }

    public void cartChange(Long userId, Long id, int delta) {
        requireOwnRow(userId, id);
        if (delta >= 0) {
            cartMapper.changeQty(id, delta);
        } else {
            // 减到 0 即移除该行（与主流电商交互一致）
            Map<String, Object> row = cartMapper.getById(id);
            int cur = row == null || row.get("qty") == null ? 0 : Integer.parseInt(String.valueOf(row.get("qty")));
            int next = cur + delta;
            if (next <= 0) {
                cartMapper.delete(id, userId);
            } else {
                cartMapper.setQty(id, next);
            }
        }
    }

    public void cartSetQty(Long userId, Long id, int qty) {
        requireOwnRow(userId, id);
        if (qty < 1) {
            cartMapper.delete(id, userId);
        } else {
            cartMapper.setQty(id, Math.min(qty, 999));
        }
    }

    public void cartChecked(Long userId, Long id, int checked) {
        if (cartMapper.setChecked(id, userId, checked == 0 ? 0 : 1) == 0) {
            throw new IllegalArgumentException("购物车行不存在或不属于当前用户");
        }
    }

    public void cartDelete(Long userId, Long id) {
        if (cartMapper.delete(id, userId) == 0) {
            throw new IllegalArgumentException("购物车行不存在或不属于当前用户");
        }
    }

    private Map<String, Object> requireOwnRow(Long userId, Long id) {
        Map<String, Object> row = cartMapper.getById(id);
        if (row == null || row.get("user_id") == null
                || !String.valueOf(row.get("user_id")).equals(String.valueOf(userId))) {
            throw new IllegalArgumentException("购物车行不存在或不属于当前用户");
        }
        return row;
    }

    // ==================== 下单结算 ====================

    /**
     * 勾选购物车行 → 校验库存 → 扣库存 → 生成一条 order_table 记录（status=0 待发货）→ 清掉已购行。
     * 订单 product 汇总 "商品A x2、商品B x1"，管理端发货视图直接可读。
     */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> checkout(Long userId, String userName, String contact, String shippingAddress,
            String remark, List<Long> cartIds) {
        if (userName == null || userName.trim().isEmpty()) {
            throw new IllegalArgumentException("收货人不能为空");
        }
        if (contact == null || contact.trim().isEmpty()) {
            throw new IllegalArgumentException("联系方式不能为空");
        }
        List<Map<String, Object>> rows = cartMapper.selectWithGoods(userId);
        if (rows.isEmpty()) {
            throw new IllegalArgumentException("购物车为空");
        }
        List<Map<String, Object>> picked = new ArrayList<>();
        BigDecimal total = BigDecimal.ZERO;
        for (Map<String, Object> r : rows) {
            boolean isTarget = (cartIds == null || cartIds.isEmpty())
                    ? "1".equals(String.valueOf(r.get("checked")))
                    : cartIds.contains(Long.valueOf(String.valueOf(r.get("id"))));
            if (!isTarget) {
                continue;
            }
            Object gs = r.get("goods_status");
            Object stock = r.get("stock");
            Object qty = r.get("qty");
            if (gs == null || !"1".equals(String.valueOf(gs))) {
                throw new IllegalArgumentException("商品「" + r.get("name") + "」已下架");
            }
            int stockN = stock == null ? 0 : Integer.parseInt(String.valueOf(stock));
            int qtyN = qty == null ? 0 : Integer.parseInt(String.valueOf(qty));
            if (qtyN < 1) {
                throw new IllegalArgumentException("商品「" + r.get("name") + "」数量非法");
            }
            if (stockN < qtyN) {
                throw new IllegalArgumentException("商品「" + r.get("name") + "」库存不足（剩 " + stockN + "）");
            }
            BigDecimal price = r.get("price") == null ? BigDecimal.ZERO
                    : new BigDecimal(String.valueOf(r.get("price")));
            total = total.add(price.multiply(BigDecimal.valueOf(qtyN)));
            picked.add(r);
        }
        if (picked.isEmpty()) {
            throw new IllegalArgumentException("请先勾选要结算的商品");
        }
        // 扣库存（条件更新，并发下不会超卖）
        for (Map<String, Object> r : picked) {
            int qtyN = Integer.parseInt(String.valueOf(r.get("qty")));
            if (goodsMapper.deductStock(Long.valueOf(String.valueOf(r.get("goods_id"))), qtyN) == 0) {
                throw new IllegalArgumentException("商品「" + r.get("name") + "」库存不足，请刷新后重试");
            }
        }
        // 汇总商品描述
        StringBuilder product = new StringBuilder();
        for (int i = 0; i < picked.size(); i++) {
            if (i > 0) {
                product.append("、");
            }
            product.append(r.get("name")).append(" x").append(r.get("qty"));
        }
        String orderId = "OD" + UUID.randomUUID().toString().replace("-", "").substring(0, 20);
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("id", orderId);
        order.put("userId", userId);
        order.put("userName", userName.trim());
        order.put("contact", contact.trim());
        order.put("product", product.toString());
        order.put("amount", total.setScale(2, RoundingMode.HALF_UP));
        order.put("paymentTime", new Date());
        order.put("shippingAddress", shippingAddress == null ? "" : shippingAddress.trim());
        order.put("status", "0");
        order.put("remark", remark == null ? "" : remark);
        orderMapper.insert(order);
        // 清掉已购购物车行
        for (Map<String, Object> r : picked) {
            cartMapper.deleteByGoods(userId, Long.valueOf(String.valueOf(r.get("goods_id"))));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("orderId", orderId);
        result.put("amount", total.setScale(2, RoundingMode.HALF_UP));
        result.put("items", picked.size());
        return result;
    }

    // ==================== 我的订单（顾客端） ====================

    public PageData<Map<String, Object>> myOrders(Long userId, int page, int limit, String status) {
        int offset = (Math.max(page, 1) - 1) * Math.max(limit, 1);
        List<Map<String, Object>> list = orderMapper.selectMyPage(userId, emptyToNull(status), offset, limit);
        int total = orderMapper.selectMyCount(userId, emptyToNull(status));
        return new PageData<>(list, total);
    }

    private String emptyToNull(String s) {
        return s == null || s.trim().isEmpty() ? null : s.trim();
    }
}
