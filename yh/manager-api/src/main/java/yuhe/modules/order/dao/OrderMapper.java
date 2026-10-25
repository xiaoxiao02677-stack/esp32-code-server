package yuhe.modules.order.dao;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderMapper {

    @Select("<script>" +
            "SELECT * FROM order_table WHERE id = #{id}" +
            "<if test=\"ownerId != null\"> AND user_id = #{ownerId}</if>" +
            "</script>")
    Map<String, Object> getById(@Param("id") String id, @Param("ownerId") Long ownerId);

    /** 顾客端「我的订单」：按下单用户过滤（user_id 由 checkout 写入），状态倒序 */
    @Select("SELECT * FROM order_table" +
            " WHERE user_id = #{userId}" +
            " AND (#{status} IS NULL OR #{status} = '' OR shipping_status = #{status})" +
            " ORDER BY create_time DESC" +
            " LIMIT #{offset}, #{limit}")
    List<Map<String, Object>> selectMyPage(@Param("userId") Long userId, @Param("status") String status,
            @Param("offset") int offset, @Param("limit") int limit);

    @Select("SELECT COUNT(*) FROM order_table" +
            " WHERE user_id = #{userId}" +
            " AND (#{status} IS NULL OR #{status} = '' OR shipping_status = #{status})")
    int selectMyCount(@Param("userId") Long userId, @Param("status") String status);

    /** 管理端列表：超管 userId 传 null 全量；普通用户强制按本人过滤（数据范围） */
    @Select("SELECT * FROM order_table" +
            " WHERE (shipping_status IS NULL OR shipping_status <> '3')" +
            " AND (#{userId} IS NULL OR user_id = #{userId})" +
            " AND (#{keyword} IS NULL OR #{keyword} = ''" +
            " OR user_name LIKE CONCAT('%', #{keyword}, '%')" +
            " OR contact LIKE CONCAT('%', #{keyword}, '%')" +
            " OR product LIKE CONCAT('%', #{keyword}, '%'))" +
            " ORDER BY create_time DESC" +
            " LIMIT #{offset}, #{limit}")
    List<Map<String, Object>> selectList(@Param("keyword") String keyword, @Param("userId") Long userId,
            @Param("offset") int offset, @Param("limit") int limit);

    @Select("SELECT COUNT(*) FROM order_table" +
            " WHERE (shipping_status IS NULL OR shipping_status <> '3')" +
            " AND (#{userId} IS NULL OR user_id = #{userId})" +
            " AND (#{keyword} IS NULL OR #{keyword} = ''" +
            " OR user_name LIKE CONCAT('%', #{keyword}, '%')" +
            " OR contact LIKE CONCAT('%', #{keyword}, '%')" +
            " OR product LIKE CONCAT('%', #{keyword}, '%'))")
    int selectCount(@Param("keyword") String keyword, @Param("userId") Long userId);

    @Insert("INSERT INTO order_table (id, user_id, user_name, contact, product, amount, pay_time, address, shipping_status, remark, create_time, update_time)" +
            " VALUES (#{id}, #{userId}, #{userName}, #{contact}, #{product}, #{amount}, #{paymentTime}, #{shippingAddress}, #{status}, #{remark}, NOW(), NOW())")
    void insert(Map<String, Object> params);

    @Update("UPDATE order_table SET" +
            " user_name = #{userName}," +
            " contact = #{contact}," +
            " product = #{product}," +
            " amount = #{amount}," +
            " pay_time = #{paymentTime}," +
            " address = #{shippingAddress}," +
            " shipping_status = #{status}," +
            " remark = #{remark}," +
            " update_time = NOW()" +
            " WHERE id = #{id}")
    void update(Map<String, Object> params);

    @Update("UPDATE order_table SET shipping_status = '3', update_time = NOW() WHERE id = #{id}")
    void delete(@Param("id") String id);

    /** 支付成功落账时间（异步通知验签通过后调用；pay_time 为 NULL 才写，避免覆盖管理员手工值） */
    @Update("UPDATE order_table SET pay_time = NOW(), update_time = NOW()" +
            " WHERE id = #{id} AND pay_time IS NULL")
    int markPaidTime(@Param("id") String id);
}
