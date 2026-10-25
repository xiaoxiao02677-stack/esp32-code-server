package yuhe.modules.order.controller;

import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import javax.imageio.ImageIO;

import org.apache.commons.codec.digest.DigestUtils;
import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import lombok.extern.slf4j.Slf4j;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.order.service.OrderShopService;

/**
 * 电商小店-商品管理。
 * 管理端读写（page/info/create/update/delete/export/toggle）须超管或 admin:goods 模块码
 * （Oauth2Realm 按展示配置发放；未配置商品模块的普通用户在此被 403 拦截）；
 * 顾客端 on-sale/categories 为匿名只读（ShiroConfig anon 放行，/shop 商店依赖）；
 * 封面 cover/upload 限管理端上传，cover/{file} 匿名下载（顾客端商品图依赖）。
 */
@Slf4j
@RestController
@RequestMapping("/goods")
public class GoodsController {

    private final OrderShopService orderShopService;

    public GoodsController(OrderShopService orderShopService) {
        this.orderShopService = orderShopService;
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @GetMapping("/page")
    public Result<PageData<Map<String, Object>>> page(
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer limit,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) Integer status) {
        return new Result<PageData<Map<String, Object>>>()
                .ok(orderShopService.goodsPage(page, limit, keyword, category, status));
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @GetMapping("/info/{id}")
    public Result<Map<String, Object>> info(@PathVariable Long id) {
        return new Result<Map<String, Object>>().ok(orderShopService.goodsInfo(id));
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @PostMapping("/create")
    public Result<Long> create(@RequestBody Map<String, Object> params) {
        return new Result<Long>().ok(orderShopService.goodsCreate(params));
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @PutMapping("/update/{id}")
    public Result<Long> update(@PathVariable Long id, @RequestBody Map<String, Object> params) {
        orderShopService.goodsUpdate(id, params);
        return new Result<Long>().ok(id);
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @DeleteMapping("/delete/{id}")
    public Result<Long> delete(@PathVariable Long id) {
        orderShopService.goodsDelete(id);
        return new Result<Long>().ok(id);
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @GetMapping("/export")
    public Result<List<Map<String, Object>>> export() {
        return new Result<List<Map<String, Object>>>().ok(orderShopService.goodsExport());
    }

    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @PutMapping("/toggle/{id}")
    public Result<Long> toggle(@PathVariable Long id, @RequestParam(defaultValue = "1") Integer status) {
        orderShopService.goodsToggle(id, status);
        return new Result<Long>().ok(id);
    }

    // ===== 顾客端 =====

    @GetMapping("/on-sale")
    public Result<List<Map<String, Object>>> onSale() {
        return new Result<List<Map<String, Object>>>().ok(orderShopService.goodsOnSale());
    }

    @GetMapping("/categories")
    public Result<List<String>> categories() {
        return new Result<List<String>>().ok(orderShopService.goodsCategories());
    }

    // ===== 封面图片上传/下载 =====
    // 独立于壁纸链路（壁纸是固件 RGB565 专用）；这里存原图，展示端 object-fit 自适应。

    private static final String COVER_DIR = "uploadfile/goods-cover";
    private static final long COVER_MAX_SIZE = 8L * 1024 * 1024;
    private static final Set<String> COVER_EXT = Set.of("png", "jpg", "jpeg", "webp", "gif");

    /** 上传商品封面：multipart 图片 → 魔数+解码双重校验 → 内容寻址落盘（同图幂等）→ 返回下载 URL。
     *  注意路径必须是 /goods/cover-upload（不能在 /goods/cover/ 下）：
     *  ShiroConfig 对 /goods/cover/* 走匿名链（顾客端下载图），上传若同路径会被匿名放过后
     *  再被权限注解拒绝（AuthorizationException→500）。 */
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:goods"}, logical = Logical.OR)
    @PostMapping("/cover-upload")
    public Result<Map<String, Object>> uploadCover(@RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new RenException(ErrorCode.UPLOAD_FILE_EMPTY);
        }
        if (file.getSize() > COVER_MAX_SIZE) {
            throw new RenException(ErrorCode.VOICE_CLONE_AUDIO_TOO_LARGE);
        }
        byte[] data;
        try {
            data = file.getBytes();
        } catch (Exception e) {
            throw new RenException(ErrorCode.UPLOAD_FILE_EMPTY);
        }
        // 魔数识别（拒绝改扩展名的非图片），ImageIO 解码兜底校验像素完整性
        String fmt = sniffImage(data);
        if (fmt == null) {
            throw new RenException(ErrorCode.UPLOAD_FILE_ERROR);
        }
        try {
            BufferedImage img = ImageIO.read(new ByteArrayInputStream(data));
            if (img == null || img.getWidth() < 1 || img.getHeight() < 1) {
                throw new RenException(ErrorCode.UPLOAD_FILE_ERROR);
            }
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException(ErrorCode.UPLOAD_FILE_ERROR);
        }
        String md5 = DigestUtils.md5Hex(data);
        String fileName = md5 + "." + fmt;
        try {
            Path dir = Paths.get(COVER_DIR).toAbsolutePath().normalize();
            Files.createDirectories(dir);
            Path target = dir.resolve(fileName).normalize();
            if (!target.startsWith(dir)) {
                throw new RenException(ErrorCode.INVALID_SYMBOL);
            }
            if (!Files.exists(target)) {
                Files.write(target, data);
            }
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("[goods-cover] 封面写入失败: {}", e.getMessage());
            throw new RenException(ErrorCode.UPLOAD_FILE_ERROR);
        }
        // 返回同源相对路径：前端页面（https 8101 管理端 / 顾客商店）直接 <img src> 加载，
        // 经 nginx /yuhe/ 反代回 8002。不拼绝对基址——https 页面加载 http 图片会被
        // 浏览器混合内容策略拦截（8144 是明文端口）。
        String url = "/yuhe/goods/cover/" + fileName;
        return new Result<Map<String, Object>>().ok(Map.of("url", url, "fileName", fileName));
    }

    /** 下载商品封面（匿名：顾客端商品图依赖；仅 32 位 md5 + 固定扩展名，杜绝目录穿越） */
    @GetMapping("/cover/{fileName}")
    public ResponseEntity<byte[]> downloadCover(@PathVariable("fileName") String fileName) {
        String ext = fileName.lastIndexOf('.') > 0
                ? fileName.substring(fileName.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT) : "";
        if (!fileName.matches("[0-9a-f]{32}\\.(png|jpg|jpeg|webp|gif)")
                || !COVER_EXT.contains(ext)) {
            throw new RenException(ErrorCode.INVALID_SYMBOL);
        }
        try {
            Path dir = Paths.get(COVER_DIR).toAbsolutePath().normalize();
            Path target = dir.resolve(fileName).normalize();
            if (!target.startsWith(dir) || !Files.exists(target)) {
                throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            }
            byte[] content = Files.readAllBytes(target);
            MediaType mt = switch (ext) {
                case "png" -> MediaType.IMAGE_PNG;
                case "gif" -> MediaType.IMAGE_GIF;
                case "webp" -> MediaType.parseMediaType("image/webp");
                default -> MediaType.IMAGE_JPEG;
            };
            return ResponseEntity.ok()
                    .contentType(mt)
                    .header(HttpHeaders.CONTENT_LENGTH, String.valueOf(content.length))
                    .body(content);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("[goods-cover] 封面读取失败 {}: {}", fileName, e.getMessage());
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
    }

    /** 魔数识别：png/jpg/webp/gif，识别不了返回 null（拒绝仅改扩展名的文件） */
    private static String sniffImage(byte[] d) {
        if (d == null || d.length < 12) {
            return null;
        }
        if ((d[0] & 0xFF) == 0x89 && d[1] == 'P' && d[2] == 'N' && d[3] == 'G') {
            return "png";
        }
        if ((d[0] & 0xFF) == 0xFF && (d[1] & 0xFF) == 0xD8 && (d[2] & 0xFF) == 0xFF) {
            return "jpg";
        }
        // RIFF....WEBP
        if (d[0] == 'R' && d[1] == 'I' && d[2] == 'F' && d[3] == 'F' && d[8] == 'W' && d[9] == 'E'
                && d[10] == 'B' && d[11] == 'P') {
            return "webp";
        }
        // GIF87a / GIF89a
        if (d[0] == 'G' && d[1] == 'I' && d[2] == 'F' && d[3] == '8' && (d[4] == '7' || d[4] == '9')
                && d[5] == 'a') {
            return "gif";
        }
        return null;
    }
}
