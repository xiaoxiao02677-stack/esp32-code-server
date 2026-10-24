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
 * 电商小店-商品表 shop_goods（Map 直查风格，与 OrderMapper 一致）
 */
@Mapper
public interface GoodsMapper {

    @Select("<script>SELECT * FROM shop_goods" +
            " <where>" +
            "  <if test='keyword != null and keyword != \"\"'>AND (name LIKE CONCAT('%', #{keyword}, '%') OR category LIKE CONCAT('%', #{keyword}, '%'))</if>" +
            "  <if test='category != null and category != \"\"'>AND category = #{category}</if>" +
            "  <if test='status != null'>AND status = #{status}</if>" +
            " </where>" +
            " ORDER BY status DESC, sort DESC, id DESC" +
            " LIMIT #{offset}, #{limit}</script>")
    List<Map<String, Object>> selectList(@Param("keyword") String keyword, @Param("category") String category,
            @Param("status") Integer status, @Param("offset") int offset, @Param("limit") int limit);

    @Select("<script>SELECT COUNT(*) FROM shop_goods" +
            " <where>" +
            "  <if test='keyword != null and keyword != \"\"'>AND (name LIKE CONCAT('%', #{keyword}, '%') OR category LIKE CONCAT('%', #{keyword}, '%'))</if>" +
            "  <if test='category != null and category != \"\"'>AND category = #{category}</if>" +
            "  <if test='status != null'>AND status = #{status}</if>" +
            " </where></script>")
    int selectCount(@Param("keyword") String keyword, @Param("category") String category,
            @Param("status") Integer status);

    @Select("SELECT * FROM shop_goods WHERE id = #{id}")
    Map<String, Object> getById(@Param("id") Long id);

    @Select("SELECT * FROM shop_goods WHERE status = 1 AND stock > 0 ORDER BY sort DESC, id DESC")
    List<Map<String, Object>> selectOnSale();

    @Select("SELECT DISTINCT category FROM shop_goods WHERE category IS NOT NULL AND category != '' ORDER BY category")
    List<String> selectCategories();

    @Insert("INSERT INTO shop_goods (name, cover, price, stock, category, status, sort, remark)" +
            " VALUES (#{name}, #{cover}, #{price}, #{stock}, #{category}, #{status}, #{sort}, #{remark})")
    @org.apache.ibatis.annotations.Options(useGeneratedKeys = true, keyProperty = "id")
    void insert(Map<String, Object> params);

    @Update("UPDATE shop_goods SET" +
            " name = #{name}," +
            " cover = #{cover}," +
            " price = #{price}," +
            " stock = #{stock}," +
            " category = #{category}," +
            " status = #{status}," +
            " sort = #{sort}," +
            " remark = #{remark}," +
            " update_time = NOW()" +
            " WHERE id = #{id}")
    void update(Map<String, Object> params);

    /** 上下架专用（只动 status，避免全字段 update 覆盖其他列） */
    @Update("UPDATE shop_goods SET status = #{status}, update_time = NOW() WHERE id = #{id}")
    void updateStatus(@Param("id") Long id, @Param("status") Integer status);

    @Update("UPDATE shop_goods SET stock = stock - #{qty}, update_time = NOW() WHERE id = #{id} AND stock >= #{qty}")
    int deductStock(@Param("id") Long id, @Param("qty") int qty);

    @Delete("DELETE FROM shop_goods WHERE id = #{id}")
    void delete(@Param("id") Long id);
}
