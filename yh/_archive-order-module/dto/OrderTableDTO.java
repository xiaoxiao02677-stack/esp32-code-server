package xiaozhi.modules.order.dto;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;
import xiaozhi.common.validator.group.AddGroup;
import xiaozhi.common.validator.group.DefaultGroup;
import xiaozhi.common.validator.group.UpdateGroup;

/**
 * 订单 DTO
 */
@Data
@Schema(description = "订单")
public class OrderTableDTO implements Serializable {

    @Schema(description = "id")
    @Null(message = "{id.null}", groups = AddGroup.class)
    @NotNull(message = "{id.require}", groups = UpdateGroup.class)
    private Long id;

    @Schema(description = "用户姓名")
    @NotNull(message = "用户姓名不能为空", groups = {AddGroup.class, UpdateGroup.class})
    private String userName;

    @Schema(description = "联系方式")
    @NotNull(message = "联系方式不能为空", groups = {AddGroup.class, UpdateGroup.class})
    private String contact;

    @Schema(description = "商品描述")
    @NotNull(message = "商品描述不能为空", groups = {AddGroup.class, UpdateGroup.class})
    private String product;

    @Schema(description = "金额")
    @NotNull(message = "金额不能为空", groups = {AddGroup.class, UpdateGroup.class})
    private BigDecimal amount;

    @Schema(description = "支付时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date payTime;

    @Schema(description = "收货地址")
    private String address;

    @Schema(description = "发货状态：0-待发货 1-已发货 2-已签收 3-已取消")
    private Integer shippingStatus;

    @Schema(description = "备注")
    private String remark;
}
