package yuhe.modules.timbre.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.common.validator.ValidatorUtils;
import yuhe.modules.timbre.dto.TimbreDataDTO;
import yuhe.modules.timbre.dto.TimbrePageDTO;
import yuhe.modules.timbre.service.TimbreService;
import yuhe.modules.timbre.vo.TimbreDetailsVO;

/**
 * 音色控制层
 *
 * @author zjy
 * @since 2025-3-21
 */
@AllArgsConstructor
@RestController
@RequestMapping("/ttsVoice")
@Tag(name = "音色管理")
public class TimbreController {
    private final TimbreService timbreService;

    @GetMapping
    @Operation(summary = "分页查找")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:voices"}, logical = Logical.OR)
    @Parameters({
            @Parameter(name = "ttsModelId", description = "对应 TTS 模型主键", required = true),
            @Parameter(name = "name", description = "音色名称"),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<TimbreDetailsVO>> page(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        TimbrePageDTO dto = new TimbrePageDTO();
        dto.setTtsModelId((String) params.get("ttsModelId"));
        dto.setName((String) params.get("name"));
        dto.setLimit((String) params.get(Constant.LIMIT));
        dto.setPage((String) params.get(Constant.PAGE));

        ValidatorUtils.validateEntity(dto);
        PageData<TimbreDetailsVO> page = timbreService.page(dto);
        return new Result<PageData<TimbreDetailsVO>>().ok(page);
    }

    @PostMapping
    @Operation(summary = "音色保存")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:voices"}, logical = Logical.OR)
    public Result<Void> save(@RequestBody TimbreDataDTO dto) {
        ValidatorUtils.validateEntity(dto);
        timbreService.save(dto);
        return new Result<>();
    }

    @PutMapping("/{id}")
    @Operation(summary = "音色修改")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:voices"}, logical = Logical.OR)
    public Result<Void> update(
            @PathVariable String id,
            @RequestBody TimbreDataDTO dto) {
        ValidatorUtils.validateEntity(dto);
        timbreService.update(id, dto);
        return new Result<>();
    }

    @PostMapping("/delete")
    @Operation(summary = "音色删除")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:voices"}, logical = Logical.OR)
    public Result<Void> delete(@RequestBody String[] ids) {
        timbreService.delete(ids);
        return new Result<>();
    }

    @PostMapping("/probe")
    @Operation(summary = "探测当前引擎支持音色并同步（删除失效+新增有效+迁移智能体引用）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:voices"}, logical = Logical.OR)
    @Parameter(name = "ttsModelId", description = "对应 TTS 模型主键", required = true)
    public Result<Map<String, Object>> probe(@RequestParam String ttsModelId) {
        Map<String, Object> report = timbreService.probeAndSync(ttsModelId);
        return new Result<Map<String, Object>>().ok(report);
    }

}