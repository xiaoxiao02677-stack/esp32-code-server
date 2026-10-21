package yuhe.modules.order.controller;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * 电商小店-购物车 shop_cart（按 user_id 隔离，uk_user_goods 唯一键防重复行）
 */
@Mapper
public interface CartMapper {

    /** 购物车行联商品信息（含下架/缺货标记，前端据此禁用勾选） */
    @Select("SELECT c.id, c.user_id, c.goods_id, c.qty, c.checked, c.update_time," +
            " g.name, g.cover, g.price, g.stock, g.category, g.status AS goods_status" +
            " FROM shop_cart c LEFT JOIN shop_goods g ON c.goods_id = g.id" +
            " WHERE c.user_id = #{userId} ORDER BY c.update_time DESC, c.id DESC")
    List<Map<String, Object>> selectWithGoods(@Param("userId") Long userId);

    @Select("SELECT * FROM shop_cart WHERE id = #{id}")
    Map<String, Object> getById(@Param("id") Long id);

    @Select("SELECT * FROM shop_cart WHERE user_id = #{userId} AND goods_id = #{goodsId}")
    Map<String, Object> findRow(@Param("userId") Long userId, @Param("goodsId") Long goodsId);

    @Insert("INSERT INTO shop_cart (user_id, goods_id, qty, checked) VALUES (#{userId}, #{goodsId}, #{qty}, 1)")
    void insert(@Param("userId") Long userId, @Param("goodsId") Long goodsId, @Param("qty") int qty);

    @Update("UPDATE shop_cart SET qty = qty + #{delta}, update_time = NOW() WHERE id = #{id}")
    void changeQty(@Param("id") Long id, @Param("delta") int delta);

    @Update("UPDATE shop_cart SET qty = #{qty}, update_time = NOW() WHERE id = #{id}")
    void setQty(@Param("id") Long id, @Param("qty") int qty);

    @Update("UPDATE shop_cart SET checked = #{checked}, update_time = NOW() WHERE id = #{id} AND user_id = #{userId}")
    int setChecked(@Param("id") Long id, @Param("userId") Long userId, @Param("checked") int checked);

    @Delete("DELETE FROM shop_cart WHERE id = #{id} AND user_id = #{userId}")
    int delete(@Param("id") Long id, @Param("userId") Long userId);

    @Delete("DELETE FROM shop_cart WHERE user_id = #{userId}")
    void clearByUser(@Param("userId") Long userId);

    @Delete("DELETE FROM shop_cart WHERE user_id = #{userId} AND goods_id = #{goodsId}")
    void deleteByGoods(@Param("userId") Long userId, @Param("goodsId") Long goodsId);
}
