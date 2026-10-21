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

    @Select("SELECT * FROM order_table WHERE id = #{id}")
    Map<String, Object> getById(@Param("id") String id);

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

    @Select("SELECT * FROM order_table" +
            " WHERE (shipping_status IS NULL OR shipping_status <> '3')" +
            " AND (#{keyword} IS NULL OR #{keyword} = ''" +
            " OR user_name LIKE CONCAT('%', #{keyword}, '%')" +
            " OR contact LIKE CONCAT('%', #{keyword}, '%')" +
            " OR product LIKE CONCAT('%', #{keyword}, '%'))" +
            " ORDER BY create_time DESC" +
            " LIMIT #{offset}, #{limit}")
    List<Map<String, Object>> selectList(@Param("keyword") String keyword, @Param("offset") int offset, @Param("limit") int limit);

    @Select("SELECT COUNT(*) FROM order_table" +
            " WHERE (shipping_status IS NULL OR shipping_status <> '3')" +
            " AND (#{keyword} IS NULL OR #{keyword} = ''" +
            " OR user_name LIKE CONCAT('%', #{keyword}, '%')" +
            " OR contact LIKE CONCAT('%', #{keyword}, '%')" +
            " OR product LIKE CONCAT('%', #{keyword}, '%'))")
    int selectCount(@Param("keyword") String keyword);

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
}
