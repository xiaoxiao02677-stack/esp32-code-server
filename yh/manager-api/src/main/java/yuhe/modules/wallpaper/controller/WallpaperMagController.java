package yuhe.modules.wallpaper.controller;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.wallpaper.dto.WallpaperDispatchDTO;
import yuhe.modules.wallpaper.dto.WallpaperRetryDTO;
import yuhe.modules.wallpaper.entity.WallpaperEntity;
import yuhe.modules.wallpaper.service.WallpaperService;
import yuhe.modules.wallpaper.vo.WallpaperTaskDetailVO;

/**
 * 壁纸管理（P1-3）
 *
 * <p>上传接口在服务端完成 RGB565 转码；下发接口先写 ai_device_config（必生效），
 * 再对在线设备走 Python 即时通道（best-effort）。鉴权范式与 OTAMagController 一致。
 */
@Tag(name = "壁纸管理", description = "壁纸上传、转码与下发")
@Slf4j
@RestController
@RequiredArgsConstructor
@RequestMapping("/wallpaperMag")
public class WallpaperMagController {

    private final WallpaperService wallpaperService;

    @PostMapping("/upload")
    @Operation(summary = "上传壁纸（PNG/JPG/WebP，≤2MB，服务端转码 RGB565）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<WallpaperEntity> upload(@RequestParam("file") MultipartFile file,
            @RequestParam(value = "name", required = false) String name) {
        return new Result<WallpaperEntity>().ok(wallpaperService.upload(file, name));
    }

    @GetMapping
    @Operation(summary = "分页查询壁纸")
    @RequiresPermissions("sys:role:normal")
    public Result<PageData<WallpaperEntity>> page(
            @RequestParam(value = "page", required = false, defaultValue = "1") Integer page,
            @RequestParam(value = "limit", required = false, defaultValue = "10") Integer limit,
            @RequestParam(value = "keyword", required = false) String keyword) {
        return new Result<PageData<WallpaperEntity>>().ok(wallpaperService.page(page, limit, keyword));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除壁纸")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> delete(@PathVariable("id") String id) {
        wallpaperService.delete(id);
        return new Result<Void>();
    }

    @PostMapping("/dispatch")
    @Operation(summary = "下发壁纸到设备/智能体分组/全部设备")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<WallpaperTaskDetailVO> dispatch(@RequestBody WallpaperDispatchDTO dto) {
        return new Result<WallpaperTaskDetailVO>().ok(wallpaperService.dispatch(dto));
    }

    @GetMapping("/task/{taskId}")
    @Operation(summary = "壁纸任务详情（含设备回执）")
    @RequiresPermissions("sys:role:normal")
    public Result<WallpaperTaskDetailVO> task(@PathVariable("taskId") String taskId) {
        return new Result<WallpaperTaskDetailVO>().ok(wallpaperService.detail(taskId));
    }

    @PostMapping("/task/{taskId}/retry")
    @Operation(summary = "重试壁纸下发")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<WallpaperTaskDetailVO> retry(@PathVariable("taskId") String taskId,
            @RequestBody(required = false) WallpaperRetryDTO dto) {
        return new Result<WallpaperTaskDetailVO>()
                .ok(wallpaperService.retry(taskId, dto == null ? null : dto.getDeviceIds()));
    }

    /**
     * 固件下载转码产物：/wallpaperMag/download/{md5}.bin（RGB565）或 {md5}.png（缩略图）。
     * 匿名可访问（ShiroConfig 放行），仅允许 32 位 md5 + 固定扩展名，杜绝目录穿越。
     */
    @GetMapping("/download/{fileName}")
    @Operation(summary = "下载壁纸文件（.bin / 缩略图 .png）")
    public ResponseEntity<byte[]> download(@PathVariable("fileName") String fileName) {
        byte[] content = wallpaperService.download(fileName);
        MediaType mediaType = fileName.endsWith(".png") ? MediaType.IMAGE_PNG : MediaType.APPLICATION_OCTET_STREAM;
        return ResponseEntity.ok()
                .contentType(mediaType)
                .header(HttpHeaders.CONTENT_LENGTH, String.valueOf(content.length))
                .body(content);
    }
}
