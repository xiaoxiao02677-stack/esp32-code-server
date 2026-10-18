package yuhe.modules.wallpaper.service.impl;

import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Date;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;

import org.apache.commons.lang3.StringUtils;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import cn.hutool.crypto.digest.DigestUtil;
import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.redis.RedisKeys;
import yuhe.common.service.impl.BaseServiceImpl;
import yuhe.common.utils.JsonUtils;
import yuhe.modules.device.dao.DeviceConfigDao;
import yuhe.modules.device.dao.DeviceDao;
import yuhe.modules.device.entity.DeviceEntity;
import yuhe.modules.sys.service.SysParamsService;
import yuhe.modules.wallpaper.client.WallpaperDispatchClient;
import yuhe.modules.wallpaper.dao.WallpaperDao;
import yuhe.modules.wallpaper.dao.WallpaperTaskDao;
import yuhe.modules.wallpaper.dao.WallpaperTaskDeviceDao;
import yuhe.modules.wallpaper.dto.WallpaperDispatchDTO;
import yuhe.modules.wallpaper.entity.WallpaperEntity;
import yuhe.modules.wallpaper.entity.WallpaperTaskDeviceEntity;
import yuhe.modules.wallpaper.entity.WallpaperTaskEntity;
import yuhe.modules.wallpaper.service.WallpaperService;
import yuhe.modules.wallpaper.vo.WallpaperTaskDetailVO;

/**
 * 壁纸管理实现（P1-3）
 *
 * <p>转码链路：源图（PNG/JPG/WebP，≤2MB）→ Java ImageIO 解码 → cover 等比缩放并居中裁切到 240x240
 * → RGB565 小端原始像素（115200 字节）→ md5 → 存储 uploadfile/{md5}.bin，同时输出 240x240 PNG 缩略图。
 *
 * <p>下发链路：ai_device_config.config_json 增量写入 wallpaper 子对象（JSON_MERGE_PATCH，保留其它键），
 * 保证设备下次启动必生效；applyMode=immediate 时再 best-effort 调用 Python 即时通道，
 * 推送失败只记日志（不回滚任务、不影响落库结果）。
 *
 * <p>回执链路：Python 写 Redis wallpaper:ack:{device_id}，任务详情读取后与 DB 明细合并汇总。
 */
@Slf4j
@Service
@AllArgsConstructor
public class WallpaperServiceImpl extends BaseServiceImpl<WallpaperDao, WallpaperEntity>
        implements WallpaperService {

    /** 壁纸像素边长（固件屏幕 240x240） */
    private static final int TARGET_SIZE = 240;

    /** 源图大小上限 2MB */
    private static final long MAX_SOURCE_SIZE = 2L * 1024 * 1024;

    /** 转码产物目录（与 OTAMagController 的 uploadfile 机制一致，相对进程工作目录） */
    private static final String UPLOAD_DIR = "uploadfile";

    /** 目标像素格式（固件契约） */
    private static final String FORMAT_RGB565 = "rgb565";

    /** 壁纸格式版本（Python/固件契约固定为 3） */
    private static final String WALLPAPER_VERSION = "3";

    private static final String SCOPE_GLOBAL = "global";

    private static final String EXT_BIN = ".bin";

    private static final String EXT_PNG = ".png";

    private static final String DOWNLOAD_PATH = "wallpaperMag/download/";

    private static final Set<String> ALLOWED_FORMATS = Set.of("png", "jpeg", "webp");

    private static final String TARGET_DEVICES = "devices";
    private static final String TARGET_GROUP = "group";
    private static final String TARGET_ALL = "all";

    private static final String APPLY_IMMEDIATE = "immediate";
    private static final String APPLY_NEXT_BOOT = "next_boot";

    private static final String STATUS_PENDING = "pending";
    private static final String STATUS_SENT = "sent";
    private static final String STATUS_FAILED = "failed";
    private static final String STATUS_APPLIED = "applied";

    private static final String ERROR_PUSH_UNREACHABLE = "即时通道不可达，配置已落库；设备直连在线或下次启动后生效";

    private final WallpaperTaskDao wallpaperTaskDao;
    private final WallpaperTaskDeviceDao wallpaperTaskDeviceDao;
    private final DeviceDao deviceDao;
    private final DeviceConfigDao deviceConfigDao;
    private final WallpaperDispatchClient wallpaperDispatchClient;
    private final SysParamsService sysParamsService;
    /** 回执 key 由 Python 以普通字符串写入，必须用 StringRedisTemplate 读取（默认 RedisTemplate 为 JSON 序列化） */
    private final StringRedisTemplate stringRedisTemplate;

    // ------------------------------------------------------------------ 壁纸资源

    @Override
    public WallpaperEntity upload(MultipartFile file, String name) {
        if (file == null || file.isEmpty()) {
            throw new RenException(ErrorCode.UPLOAD_FILE_EMPTY);
        }
        if (file.getSize() > MAX_SOURCE_SIZE) {
            throw formatError("源图不能超过 2MB");
        }
        String originalFilename = file.getOriginalFilename();
        String ext = extensionOf(originalFilename);
        if (!Set.of("png", "jpg", "jpeg", "webp").contains(ext)) {
            throw formatError("只支持 PNG/JPG/WebP 格式");
        }

        byte[] source;
        try {
            source = file.getBytes();
        } catch (Exception e) {
            log.error("[wallpaper] 读取上传文件失败: {}", e.getMessage());
            throw formatError("源图读取失败");
        }
        String sniffed = sniffFormat(source);
        if (sniffed == null || !ALLOWED_FORMATS.contains(sniffed)) {
            throw formatError("只支持 PNG/JPG/WebP 格式");
        }

        BufferedImage sourceImage = decode(source, sniffed);
        BufferedImage square = coverSquare(sourceImage);
        byte[] bin = toRgb565LittleEndian(square);
        byte[] thumbPng = toPng(square);

        String md5 = DigestUtil.md5Hex(bin);
        String url = buildDownloadUrl(md5 + EXT_BIN);
        String thumbUrl = buildDownloadUrl(md5 + EXT_PNG);

        // 内容寻址：同一张图重复上传直接复用，避免固件重复下载同一份数据
        WallpaperEntity exists = baseDao.selectOne(new QueryWrapper<WallpaperEntity>()
                .eq("md5", md5).last("limit 1"));
        if (exists != null) {
            log.info("[wallpaper] 相同内容已存在，复用记录 id={} md5={}", exists.getId(), md5);
            return exists;
        }

        store(md5 + EXT_BIN, bin);
        store(md5 + EXT_PNG, thumbPng);

        WallpaperEntity entity = new WallpaperEntity();
        entity.setName(resolveName(name, originalFilename));
        entity.setUrl(url);
        entity.setThumbUrl(thumbUrl);
        entity.setMd5(md5);
        entity.setSize(bin.length);
        entity.setWidth(TARGET_SIZE);
        entity.setHeight(TARGET_SIZE);
        entity.setFormat(FORMAT_RGB565);
        entity.setScope(SCOPE_GLOBAL);
        baseDao.insert(entity);
        log.info("[wallpaper] 转码完成 id={} md5={} size={} source={}x{} srcBytes={}",
                entity.getId(), md5, bin.length, sourceImage.getWidth(), sourceImage.getHeight(), source.length);
        return entity;
    }

    @Override
    public PageData<WallpaperEntity> page(Integer page, Integer limit, String keyword) {
        long current = page == null || page < 1 ? 1L : page;
        long size = limit == null || limit < 1 ? 10L : limit;
        Page<WallpaperEntity> p = new Page<>(current, size);
        QueryWrapper<WallpaperEntity> wrapper = new QueryWrapper<WallpaperEntity>()
                .like(StringUtils.isNotBlank(keyword), "name", StringUtils.trimToEmpty(keyword))
                .orderByDesc("create_date");
        baseDao.selectPage(p, wrapper);
        return new PageData<>(p.getRecords(), p.getTotal());
    }

    @Override
    public void delete(String id) {
        WallpaperEntity entity = baseDao.selectById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.WALLPAPER_NOT_FOUND);
        }
        // 文件按 md5 内容寻址且可能被历史任务引用（设备下次启动仍要下载），只删元数据
        baseDao.deleteById(id);
    }

    @Override
    public byte[] download(String fileName) {
        if (fileName == null || !fileName.matches("[a-f0-9]{32}\\.(bin|png)")) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        Path dir = Paths.get(UPLOAD_DIR).toAbsolutePath().normalize();
        Path file = dir.resolve(fileName).normalize();
        if (!file.startsWith(dir) || !Files.isRegularFile(file)) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        try {
            return Files.readAllBytes(file);
        } catch (Exception e) {
            log.error("[wallpaper] 读取壁纸文件失败 file={}: {}", fileName, e.getMessage());
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
    }

    // ------------------------------------------------------------------ 下发

    @Override
    @Transactional(rollbackFor = Exception.class)
    public WallpaperTaskDetailVO dispatch(WallpaperDispatchDTO dto) {
        if (dto == null || StringUtils.isBlank(dto.getWallpaperId())) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        WallpaperEntity wallpaper = baseDao.selectById(dto.getWallpaperId());
        if (wallpaper == null) {
            throw new RenException(ErrorCode.WALLPAPER_NOT_FOUND);
        }
        String targetType = normalizeTargetType(dto.getTargetType());
        List<DeviceEntity> devices = resolveDevices(targetType, dto);
        if (devices.isEmpty()) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        String applyMode = APPLY_NEXT_BOOT.equalsIgnoreCase(StringUtils.trimToEmpty(dto.getApplyMode()))
                ? APPLY_NEXT_BOOT
                : APPLY_IMMEDIATE;

        WallpaperTaskEntity task = new WallpaperTaskEntity();
        task.setWallpaperId(wallpaper.getId());
        task.setTargetType(targetType);
        task.setTargetIds(targetIdsJson(targetType, dto));
        task.setApplyMode(applyMode);
        task.setStatus(STATUS_PENDING);
        task.setTotal(devices.size());
        task.setSent(0);
        task.setSuccess(0);
        task.setFailed(0);
        wallpaperTaskDao.insert(task);

        Map<String, Object> configWallpaper = configWallpaper(wallpaper);
        for (DeviceEntity device : devices) {
            insertTaskDevice(task.getId(), device.getId(), STATUS_PENDING, null);
            writeDeviceConfig(device, configWallpaper);
        }

        if (APPLY_IMMEDIATE.equals(applyMode)) {
            push(task, devices, wallpaper);
        }
        refreshTaskStats(task);
        return buildDetail(task);
    }

    @Override
    public WallpaperTaskDetailVO detail(String taskId) {
        WallpaperTaskEntity task = wallpaperTaskDao.selectById(taskId);
        if (task == null) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        return buildDetail(task);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public WallpaperTaskDetailVO retry(String taskId, List<String> deviceIds) {
        WallpaperTaskEntity task = wallpaperTaskDao.selectById(taskId);
        if (task == null) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        WallpaperEntity wallpaper = baseDao.selectById(task.getWallpaperId());
        if (wallpaper == null) {
            throw new RenException(ErrorCode.WALLPAPER_NOT_FOUND);
        }
        QueryWrapper<WallpaperTaskDeviceEntity> wrapper = new QueryWrapper<WallpaperTaskDeviceEntity>()
                .eq("task_id", taskId);
        List<String> filter = deviceIds == null ? List.of()
                : deviceIds.stream().filter(StringUtils::isNotBlank).distinct().toList();
        if (!filter.isEmpty()) {
            wrapper.in("device_id", filter);
        } else {
            wrapper.in("status", List.of(STATUS_PENDING, STATUS_FAILED, STATUS_SENT));
        }
        List<WallpaperTaskDeviceEntity> rows = wallpaperTaskDeviceDao.selectList(wrapper);
        if (rows.isEmpty()) {
            log.info("[wallpaper] 任务无可重试设备 task={}", taskId);
            return buildDetail(task);
        }

        List<String> deviceIdsToPush = rows.stream().map(WallpaperTaskDeviceEntity::getDeviceId).toList();
        for (WallpaperTaskDeviceEntity row : rows) {
            row.setStatus(STATUS_PENDING);
            row.setError(null);
            row.setAckTime(null);
            wallpaperTaskDeviceDao.updateById(row);
        }
        Map<String, DeviceEntity> deviceMap = loadDevices(deviceIdsToPush);
        List<DeviceEntity> devices = new ArrayList<>();
        for (String deviceId : deviceIdsToPush) {
            DeviceEntity device = deviceMap.get(deviceId);
            if (device != null) {
                devices.add(device);
            }
        }
        // 重试语义为「再推一次」，与任务最初的 applyMode 无关
        push(task, devices, wallpaper);
        refreshTaskStats(task);
        return buildDetail(task);
    }

    /**
     * 即时推送：在线通道 best-effort。Python 返回的 sent/offline 分别落「已推送」与「待下次启动」，
     * 通道不可用时全部标记 failed（device_config 已落库，设备下次启动仍会生效）。
     */
    private void push(WallpaperTaskEntity task, List<DeviceEntity> devices, WallpaperEntity wallpaper) {
        Map<String, String> macById = devices.stream()
                .filter(d -> StringUtils.isNotBlank(d.getMacAddress()))
                .collect(Collectors.toMap(DeviceEntity::getId, DeviceEntity::getMacAddress, (a, b) -> a));
        WallpaperDispatchClient.DispatchResult result = null;
        if (macById.isEmpty()) {
            log.warn("[wallpaper] 无可推送设备（MAC 为空） task={}", task.getId());
        } else {
            result = wallpaperDispatchClient.dispatch(
                    macById.values().stream().distinct().toList(), pythonWallpaper(wallpaper));
        }

        List<WallpaperTaskDeviceEntity> rows = wallpaperTaskDeviceDao.selectList(
                new QueryWrapper<WallpaperTaskDeviceEntity>().eq("task_id", task.getId()));
        for (WallpaperTaskDeviceEntity row : rows) {
            if (!STATUS_PENDING.equals(row.getStatus())) {
                continue;
            }
            String mac = macById.get(row.getDeviceId());
            if (mac == null) {
                row.setStatus(STATUS_FAILED);
                row.setError("设备 MAC 为空，无法下发");
            } else if (result == null || !result.isAccepted()) {
                row.setStatus(STATUS_FAILED);
                row.setError(ERROR_PUSH_UNREACHABLE);
            } else if (result.isOffline(mac)) {
                row.setStatus(STATUS_PENDING);
                // offline 含「need_bind / MQTT 网关代连」两类，文案不能承诺下次启动一定生效
                row.setError("设备非直连在线（离线/未绑定/MQTT 网关），配置已落库；直连在线后生效");
            } else if (result.isQueued(mac)) {
                row.setStatus(STATUS_PENDING);
                // queued：设备仅心跳在线、文本通道（WS）未建立；Python 已入待补投队列，
                // 由「设备 WS 上线 / 心跳重连 / 30s 巡检」三个触发点自动补投并回执
                row.setError("设备文本通道未就绪（心跳在线），已排队；设备上线后自动补投，"
                        + "每次下发只保留最新一张，下次启动亦会生效");
            } else {
                row.setStatus(STATUS_SENT);
                row.setError(null);
            }
            wallpaperTaskDeviceDao.updateById(row);
        }
    }

    /**
     * 把 wallpaper 对象增量写入设备云端配置（保留 volume/brightness 等既有键）
     */
    private void writeDeviceConfig(DeviceEntity device, Map<String, Object> configWallpaper) {
        try {
            Map<String, Object> delta = new LinkedHashMap<>();
            delta.put("wallpaper", configWallpaper);
            Date now = new Date();
            deviceConfigDao.upsertMergePatch(device.getId(), JsonUtils.toJsonString(delta), null, null, null, now);
        } catch (Exception e) {
            log.error("[wallpaper] 写入设备配置失败 deviceId={}: {}", device.getId(), e.getMessage());
        }
    }

    private void insertTaskDevice(String taskId, String deviceId, String status, String error) {
        WallpaperTaskDeviceEntity row = new WallpaperTaskDeviceEntity();
        row.setTaskId(taskId);
        row.setDeviceId(deviceId);
        row.setStatus(status);
        row.setError(error);
        wallpaperTaskDeviceDao.insert(row);
    }

    /**
     * 按 DB 明细回写任务统计（回执成功数由 detail 实时汇总，这里只落推送结果）
     */
    private void refreshTaskStats(WallpaperTaskEntity task) {
        List<WallpaperTaskDeviceEntity> rows = wallpaperTaskDeviceDao.selectList(
                new QueryWrapper<WallpaperTaskDeviceEntity>().eq("task_id", task.getId()));
        int sent = 0;
        int failed = 0;
        for (WallpaperTaskDeviceEntity row : rows) {
            if (STATUS_SENT.equals(row.getStatus()) || STATUS_APPLIED.equals(row.getStatus())) {
                sent++;
            }
            if (STATUS_FAILED.equals(row.getStatus())) {
                failed++;
            }
        }
        task.setTotal(rows.size());
        task.setSent(sent);
        task.setFailed(failed);
        task.setSuccess(0);
        task.setStatus(overallStatus(rows.size(), sent, 0, failed));
        wallpaperTaskDao.updateById(task);
    }

    // ------------------------------------------------------------------ 详情汇总

    private WallpaperTaskDetailVO buildDetail(WallpaperTaskEntity task) {
        List<WallpaperTaskDeviceEntity> rows = wallpaperTaskDeviceDao.selectList(
                new QueryWrapper<WallpaperTaskDeviceEntity>().eq("task_id", task.getId()).orderByAsc("id"));
        Map<String, DeviceEntity> deviceMap = loadDevices(
                rows.stream().map(WallpaperTaskDeviceEntity::getDeviceId).toList());

        int sent = 0;
        int success = 0;
        int failed = 0;
        List<WallpaperTaskDetailVO.Device> items = new ArrayList<>(rows.size());
        for (WallpaperTaskDeviceEntity row : rows) {
            DeviceEntity device = deviceMap.get(row.getDeviceId());
            String mac = device == null ? null : device.getMacAddress();
            String status = row.getStatus();
            String error = row.getError();

            Ack ack = readAck(mac);
            if (ack != null && !isStale(ack, task)) {
                if (ack.success) {
                    status = STATUS_APPLIED;
                    error = null;
                } else {
                    status = STATUS_FAILED;
                    error = StringUtils.isBlank(ack.reason) ? "设备应用失败" : ack.reason;
                }
            }

            if (STATUS_SENT.equals(status) || STATUS_APPLIED.equals(status)) {
                sent++;
            }
            if (STATUS_APPLIED.equals(status)) {
                success++;
            }
            if (STATUS_FAILED.equals(status)) {
                failed++;
            }

            WallpaperTaskDetailVO.Device item = new WallpaperTaskDetailVO.Device();
            item.setDeviceId(row.getDeviceId());
            item.setMac(mac);
            item.setStatus(status);
            item.setError(error);
            items.add(item);
        }

        WallpaperTaskDetailVO vo = new WallpaperTaskDetailVO();
        vo.setTaskId(task.getId());
        vo.setTotal(rows.size());
        vo.setSent(sent);
        vo.setSuccess(success);
        vo.setFailed(failed);
        vo.setStatus(overallStatus(rows.size(), sent, success, failed));
        vo.setDevices(items);
        return vo;
    }

    /**
     * 任务状态：有成功也有失败为 partial；全失败为 failed；有推送/成功为 sent；否则 pending
     */
    private String overallStatus(int total, int sent, int success, int failed) {
        if (total == 0) {
            return STATUS_PENDING;
        }
        if (failed > 0 && failed < total) {
            return "partial";
        }
        if (failed == total) {
            return STATUS_FAILED;
        }
        if (sent > 0 || success > 0) {
            return STATUS_SENT;
        }
        return STATUS_PENDING;
    }

    private Map<String, DeviceEntity> loadDevices(List<String> deviceIds) {
        List<String> ids = deviceIds.stream().filter(StringUtils::isNotBlank).distinct().toList();
        if (ids.isEmpty()) {
            return Map.of();
        }
        List<DeviceEntity> devices = deviceDao.selectList(
                new QueryWrapper<DeviceEntity>().in("id", ids));
        return devices.stream().collect(Collectors.toMap(DeviceEntity::getId, d -> d, (a, b) -> a));
    }

    /**
     * 读取 Python 写回的回执：key=wallpaper:ack:{device_id}，value=JSON{version,status,reason,ts}
     */
    private Ack readAck(String macAddress) {
        if (StringUtils.isBlank(macAddress)) {
            return null;
        }
        String raw = readAckRaw(macAddress);
        if (StringUtils.isBlank(raw)) {
            return null;
        }
        try {
            Map<String, Object> map = JsonUtils.parseMap(raw);
            if (map == null) {
                return null;
            }
            Ack ack = new Ack();
            Object status = map.get("status");
            ack.success = status != null && Set.of("ok", "success", "applied", "done")
                    .contains(status.toString().toLowerCase(Locale.ROOT));
            Object reason = map.get("reason");
            ack.reason = reason == null ? null : reason.toString();
            ack.ts = toEpochMillis(map.get("ts"));
            return ack;
        } catch (Exception e) {
            log.warn("[wallpaper] 回执解析失败 mac={}: {}", macAddress, e.getMessage());
            return null;
        }
    }

    /**
     * 逐个别名尝试读取回执 key。
     * Python 侧回执用设备 WS 上报的 device-id 原值（hello 头），而库里的 mac_address
     * 可能是冒号/无冒号、大小写、yuhe- 前缀等不同写法，逐个兜底避免漏读。
     */
    private String readAckRaw(String macAddress) {
        Set<String> candidates = new LinkedHashSet<>();
        String lower = macAddress.toLowerCase(Locale.ROOT);
        String compact = lower.replace(":", "");
        candidates.add(macAddress);
        candidates.add(lower);
        candidates.add(compact);
        candidates.add("yuhe-" + lower);
        candidates.add("yuhe-" + compact);
        for (String candidate : candidates) {
            String raw = stringRedisTemplate.opsForValue().get(RedisKeys.getWallpaperAckKey(candidate));
            if (StringUtils.isNotBlank(raw)) {
                return raw;
            }
        }
        return null;
    }

    /** ts 允许秒或毫秒；无法解析时返回 null（不做过期判断） */
    private Long toEpochMillis(Object ts) {
        if (!(ts instanceof Number number)) {
            return null;
        }
        long value = number.longValue();
        if (value <= 0) {
            return null;
        }
        return value < 1_000_000_000_000L ? value * 1000 : value;
    }

    /** 回执时间早于任务创建时间（含 5s 容差）视为上一轮遗留，不参与本次汇总 */
    private boolean isStale(Ack ack, WallpaperTaskEntity task) {
        return ack.ts != null && task.getCreateDate() != null
                && ack.ts + 5000 < task.getCreateDate().getTime();
    }

    private static final class Ack {
        private boolean success;
        private String reason;
        private Long ts;
    }

    // ------------------------------------------------------------------ 目标解析

    private String normalizeTargetType(String targetType) {
        String type = StringUtils.trimToEmpty(targetType).toLowerCase();
        if (type.isEmpty()) {
            return TARGET_DEVICES;
        }
        if (!TARGET_DEVICES.equals(type) && !TARGET_GROUP.equals(type) && !TARGET_ALL.equals(type)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        return type;
    }

    private List<DeviceEntity> resolveDevices(String targetType, WallpaperDispatchDTO dto) {
        switch (targetType) {
            case TARGET_ALL:
                return deviceDao.selectList(null);
            case TARGET_GROUP: {
                List<String> agentIds = dto.getAgentIds() == null ? List.of()
                        : dto.getAgentIds().stream().filter(StringUtils::isNotBlank).distinct().toList();
                if (agentIds.isEmpty()) {
                    return List.of();
                }
                return deviceDao.selectList(new QueryWrapper<DeviceEntity>().in("agent_id", agentIds));
            }
            default: {
                List<String> deviceIds = dto.getDeviceIds() == null ? List.of()
                        : dto.getDeviceIds().stream().filter(StringUtils::isNotBlank).distinct().toList();
                if (deviceIds.isEmpty()) {
                    return List.of();
                }
                Map<String, DeviceEntity> map = loadDevices(deviceIds);
                List<DeviceEntity> ordered = new ArrayList<>();
                for (String id : new LinkedHashSet<>(deviceIds)) {
                    DeviceEntity device = map.get(id);
                    if (device != null) {
                        ordered.add(device);
                    }
                }
                return ordered;
            }
        }
    }

    private String targetIdsJson(String targetType, WallpaperDispatchDTO dto) {
        List<String> ids;
        if (TARGET_GROUP.equals(targetType)) {
            ids = dto.getAgentIds();
        } else if (TARGET_DEVICES.equals(targetType)) {
            ids = dto.getDeviceIds();
        } else {
            return null;
        }
        if (ids == null || ids.isEmpty()) {
            return null;
        }
        return JsonUtils.toJsonString(ids.stream().filter(StringUtils::isNotBlank).distinct().toList());
    }

    // ------------------------------------------------------------------ 转码

    /** 魔数识别源图格式，避免仅凭扩展名（改扩展名的非图片会被拒绝） */
    private String sniffFormat(byte[] data) {
        if (data.length >= 8 && (data[0] & 0xFF) == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G') {
            return "png";
        }
        if (data.length >= 3 && (data[0] & 0xFF) == 0xFF && (data[1] & 0xFF) == 0xD8 && (data[2] & 0xFF) == 0xFF) {
            return "jpeg";
        }
        if (data.length >= 12 && data[0] == 'R' && data[1] == 'I' && data[2] == 'F' && data[3] == 'F'
                && data[8] == 'W' && data[9] == 'E' && data[10] == 'B' && data[11] == 'P') {
            return "webp";
        }
        return null;
    }

    private BufferedImage decode(byte[] source, String format) {
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(source))) {
            if (input == null) {
                throw formatError("源图解码失败");
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                // 标准 JDK 不带 WebP 解码器；装上插件后本分支自动可用
                throw formatError("服务端暂不支持 " + format.toUpperCase() + " 解码，请改为 PNG/JPG");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                BufferedImage image = reader.read(0);
                if (image == null || image.getWidth() <= 0 || image.getHeight() <= 0) {
                    throw formatError("源图解码失败");
                }
                return image;
            } finally {
                reader.dispose();
            }
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("[wallpaper] 源图解码异常: {}", e.getMessage());
            throw formatError("源图解码失败");
        }
    }

    /** cover：等比放大到铺满 240x240 后居中裁切（不拉伸变形） */
    private BufferedImage coverSquare(BufferedImage source) {
        BufferedImage target = new BufferedImage(TARGET_SIZE, TARGET_SIZE, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = target.createGraphics();
        try {
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            // 透明区域按黑色处理（与屏幕背景一致）
            g.fillRect(0, 0, TARGET_SIZE, TARGET_SIZE);
            double scale = Math.max((double) TARGET_SIZE / source.getWidth(),
                    (double) TARGET_SIZE / source.getHeight());
            int drawWidth = Math.max(TARGET_SIZE, (int) Math.round(source.getWidth() * scale));
            int drawHeight = Math.max(TARGET_SIZE, (int) Math.round(source.getHeight() * scale));
            g.drawImage(source, (TARGET_SIZE - drawWidth) / 2, (TARGET_SIZE - drawHeight) / 2,
                    drawWidth, drawHeight, null);
        } finally {
            g.dispose();
        }
        return target;
    }

    /** RGB565 小端：value = (r5&lt;&lt;11)|(g6&lt;&lt;5)|b5，低字节在前 */
    private byte[] toRgb565LittleEndian(BufferedImage image) {
        int[] pixels = image.getRGB(0, 0, TARGET_SIZE, TARGET_SIZE, null, 0, TARGET_SIZE);
        byte[] out = new byte[TARGET_SIZE * TARGET_SIZE * 2];
        int index = 0;
        for (int pixel : pixels) {
            int r = (pixel >> 16) & 0xFF;
            int g = (pixel >> 8) & 0xFF;
            int b = pixel & 0xFF;
            int value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
            out[index++] = (byte) (value & 0xFF);
            out[index++] = (byte) ((value >> 8) & 0xFF);
        }
        return out;
    }

    private byte[] toPng(BufferedImage image) {
        try (ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            if (!ImageIO.write(image, "png", out)) {
                throw formatError("缩略图生成失败");
            }
            return out.toByteArray();
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("[wallpaper] 缩略图生成失败: {}", e.getMessage());
            throw formatError("缩略图生成失败");
        }
    }

    // ------------------------------------------------------------------ 存储/URL

    private void store(String fileName, byte[] content) {
        try {
            Path dir = Paths.get(UPLOAD_DIR).toAbsolutePath().normalize();
            Files.createDirectories(dir);
            Path file = dir.resolve(fileName).normalize();
            if (!file.startsWith(dir)) {
                throw formatError("文件名非法");
            }
            if (Files.exists(file)) {
                return;
            }
            Files.write(file, content);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            log.error("[wallpaper] 文件写入失败 file={}: {}", fileName, e.getMessage());
            throw formatError("壁纸文件写入失败");
        }
    }

    /**
     * 下载地址与 OTA 同源（server.ota），把 /ota/ 段替换为 /wallpaperMag/download/，
     * 保证固件侧访问的域名/端口/反代前缀与现有 OTA 一致。
     */
    private String buildDownloadUrl(String fileName) {
        String base = sysParamsService.getValue(Constant.SERVER_OTA, true);
        String path = DOWNLOAD_PATH + fileName;
        if (StringUtils.isBlank(base) || "null".equals(base)) {
            return "/" + path;
        }
        if (base.contains("/ota/")) {
            return base.replace("/ota/", "/" + path);
        }
        return base.endsWith("/") ? base + path : base + "/" + path;
    }

    private String resolveName(String name, String originalFilename) {
        String value = StringUtils.trimToNull(name);
        if (value == null) {
            value = StringUtils.trimToNull(StringUtils.substringBeforeLast(
                    Objects.toString(originalFilename, ""), "."));
        }
        if (value == null) {
            value = "wallpaper";
        }
        return value.length() > 64 ? value.substring(0, 64) : value;
    }

    private String extensionOf(String originalFilename) {
        String filename = StringUtils.trimToEmpty(originalFilename);
        int dot = filename.lastIndexOf('.');
        return dot < 0 ? "" : filename.substring(dot + 1).toLowerCase();
    }

    private RenException formatError(String message) {
        RenException exception = new RenException(ErrorCode.WALLPAPER_FORMAT_INVALID);
        exception.setMsg(message);
        return exception;
    }

    /** 写入 ai_device_config 的 wallpaper 子对象（固件下次启动读取的完整字段） */
    private Map<String, Object> configWallpaper(WallpaperEntity wallpaper) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("version", wallpaperVersion(wallpaper));
        value.put("url", wallpaper.getUrl());
        value.put("md5", wallpaper.getMd5());
        value.put("size", wallpaper.getSize());
        value.put("width", wallpaper.getWidth());
        value.put("height", wallpaper.getHeight());
        value.put("format", wallpaper.getFormat());
        value.put("scope", wallpaper.getScope());
        return value;
    }

    /** Python 即时通道契约对象（字段与 §4.9 契约严格一致） */
    private Map<String, Object> pythonWallpaper(WallpaperEntity wallpaper) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("version", wallpaperVersion(wallpaper));
        value.put("url", wallpaper.getUrl());
        value.put("md5", wallpaper.getMd5());
        value.put("size", wallpaper.getSize());
        value.put("format", wallpaper.getFormat());
        return value;
    }

    /**
     * 壁纸版本号（固件幂等判据）：按内容寻址，version 相同 = 同一张图。
     * 若用固定常量，固件在收到第二张不同壁纸时会因 version 未变而跳过下载，
     * 导致换图永远不生效；md5 派生后「同图重复下发 → 幂等跳过，换图 → 必下载」。
     */
    private String wallpaperVersion(WallpaperEntity wallpaper) {
        String md5 = wallpaper.getMd5();
        return (md5 == null || md5.isBlank()) ? WALLPAPER_VERSION : WALLPAPER_VERSION + "-" + md5;
    }
}
