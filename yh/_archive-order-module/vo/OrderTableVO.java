package yuhe.modules.order.vo;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import yuhe.common.utils.DateUtils;

/**
 * 订单 VO
 */
@Data
@Schema(description = "订单")
public class OrderTableVO implements Serializable {

    @Schema(description = "id")
    private String id;

    @Schema(description = "用户姓名")
    private String userName;

    @Schema(description = "联系方式")
    private String contact;

    @Schema(description = "商品描述")
    private String product;

    @Schema(description = "金额")
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

    @Schema(description = "创建者ID")
    private Long creator;

    @Schema(description = "创建者用户名")
    private String creatorName;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;

    @Schema(description = "更新者ID")
    private Long updater;

    @Schema(description = "更新者用户名")
    private String updaterName;

    @Schema(description = "更新时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date updateDate;
}
