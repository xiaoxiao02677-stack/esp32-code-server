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
    
    @Select("SELECT * FROM order_table" +
            " WHERE (:keyword IS NULL OR :keyword = '' OR user_name LIKE CONCAT('%', #{keyword}, '%') OR contact LIKE CONCAT('%', #{keyword}, '%'))" +
            " ORDER BY create_time DESC" +
            " LIMIT #{offset}, #{limit}")
    List<Map<String, Object>> selectList(@Param("keyword") String keyword, @Param("offset") int offset, @Param("limit") int limit);
    
    @Select("SELECT COUNT(*) FROM order_table" +
            " WHERE (:keyword IS NULL OR :keyword = '' OR user_name LIKE CONCAT('%', #{keyword}, '%') OR contact LIKE CONCAT('%', #{keyword}, '%'))")
    int selectCount(@Param("keyword") String keyword);
    
    @Insert("INSERT INTO order_table (id, user_name, contact, product, amount, pay_time, address, shipping_status, remark, create_time, update_time)" +
            " VALUES (#{id}, #{userName}, #{contact}, #{product}, #{amount}, #{paymentTime}, #{shippingAddress}, #{status}, #{remark}, NOW(), NOW())")
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
