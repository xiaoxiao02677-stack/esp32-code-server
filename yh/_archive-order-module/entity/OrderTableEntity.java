package yuhe.modules.order.entity;

import java.math.BigDecimal;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 订单表
 */
@Data
@TableName("order_table")
public class OrderTableEntity {
    /**
     * 主键（UUID字符串）
     */
    @TableId
    private String id;
    /**
     * 用户姓名
     */
    private String userName;
    /**
     * 联系方式
     */
    private String contact;
    /**
     * 商品描述
     */
    private String product;
    /**
     * 金额
     */
    private BigDecimal amount;
    /**
     * 支付时间
     */
    private Date payTime;
    /**
     * 收货地址
     */
    private String address;
    /**
     * 发货状态：0-待发货 1-已发货 2-已签收 3-已取消
     */
    private Integer shippingStatus;
    /**
     * 备注
     */
    private String remark;
    /**
     * 软删除标记 0-正常 1-已删除
     */
    @TableLogic
    private Integer deleted;
    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private Date createTime;
    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Date updateTime;
}
