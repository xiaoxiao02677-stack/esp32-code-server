package yuhe.modules.order.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("order_table")
public class OrderEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String userName;
    private String contact;
    private String product;
    private Double amount;
    private Date paymentTime;
    private String shippingAddress;
    private String status;
    private String remark;
    private Date createDate;
    private Date updateDate;
}
