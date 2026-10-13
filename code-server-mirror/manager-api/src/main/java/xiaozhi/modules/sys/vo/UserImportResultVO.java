package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 批量导入结果
 */
@Data
@Schema(description = "批量导入结果")
public class UserImportResultVO implements Serializable {

    @Schema(description = "成功用户名列表")
    private List<String> success;

    @Schema(description = "失败明细 [{username, reason}]")
    private List<FailedItem> failed;

    @Data
    @Schema(description = "失败明细项")
    public static class FailedItem implements Serializable {
        @Schema(description = "用户名")
        private String username;
        @Schema(description = "失败原因")
        private String reason;
    }
}
