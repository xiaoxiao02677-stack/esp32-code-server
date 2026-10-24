package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * 电商小店-支付流水 shop_payment（支付宝预接入）
 */
@Mapper
public interface ShopPaymentMapper {

    @Select("SELECT * FROM shop_payment WHERE out_trade_no = #{outTradeNo}")
    Map<String, Object> getByOutTradeNo(@Param("outTradeNo") String outTradeNo);

    @Select("SELECT * FROM shop_payment WHERE order_id = #{orderId} ORDER BY id DESC LIMIT 1")
    Map<String, Object> getLatestByOrder(@Param("orderId") String orderId);

    @Insert("INSERT INTO shop_payment (out_trade_no, order_id, user_id, amount, status, channel)" +
            " VALUES (#{outTradeNo}, #{orderId}, #{userId}, #{amount}, 0, 'alipay')")
    void insert(@Param("outTradeNo") String outTradeNo, @Param("orderId") String orderId,
            @Param("userId") Long userId, @Param("amount") java.math.BigDecimal amount);

    /** 回调落账：仅当仍处于待支付(0)时置为已支付(1)，返回受影响行数——天然幂等（重复通知第二次 update 命中 0 行） */
    @Update("UPDATE shop_payment SET status = 1, trade_no = #{tradeNo}, buyer_id = #{buyerId}," +
            " gmt_payment = #{gmtPayment}, notify_raw = #{notifyRaw}, update_time = NOW()" +
            " WHERE out_trade_no = #{outTradeNo} AND status = 0")
    int markPaid(@Param("outTradeNo") String outTradeNo, @Param("tradeNo") String tradeNo,
            @Param("buyerId") String buyerId, @Param("gmtPayment") String gmtPayment,
            @Param("notifyRaw") String notifyRaw);

    @Update("UPDATE shop_payment SET status = 2, update_time = NOW()" +
            " WHERE order_id = #{orderId} AND status = 0")
    int closePendingByOrder(@Param("orderId") String orderId);

    @Select("SELECT * FROM shop_payment WHERE order_id = #{orderId} ORDER BY id DESC")
    List<Map<String, Object>> listByOrder(@Param("orderId") String orderId);
}
