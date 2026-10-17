package xiaozhi.modules.wallpaper.service;

import java.util.List;

import org.springframework.web.multipart.MultipartFile;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.wallpaper.dto.WallpaperDispatchDTO;
import xiaozhi.modules.wallpaper.entity.WallpaperEntity;
import xiaozhi.modules.wallpaper.vo.WallpaperTaskDetailVO;

/**
 * 壁纸管理（P1-3）
 */
public interface WallpaperService extends BaseService<WallpaperEntity> {

    /**
     * 上传源图（PNG/JPG/WebP，≤2MB），服务端转码为 240x240 RGB565 小端 .bin 并生成 PNG 缩略图
     *
     * @param file 源图
     * @param name 壁纸名称，为空时取原始文件名（去扩展名）
     * @return 壁纸元数据（id/name/url/thumbUrl/md5/size/width/height/format）
     */
    WallpaperEntity upload(MultipartFile file, String name);

    /**
     * 分页查询壁纸
     */
    PageData<WallpaperEntity> page(Integer page, Integer limit, String keyword);

    /**
     * 删除壁纸元数据（已生成的文件按内容寻址保留，避免影响进行中的任务）
     */
    void delete(String id);

    /**
     * 下发壁纸：写 ai_device_config.wallpaper + 建任务明细 + 在线设备即时推送（best-effort）
     */
    WallpaperTaskDetailVO dispatch(WallpaperDispatchDTO dto);

    /**
     * 任务详情：合并 Python 写回的 Redis 回执（wallpaper:ack:{device_id}）实时汇总
     */
    WallpaperTaskDetailVO detail(String taskId);

    /**
     * 重试下发（deviceIds 为空表示该任务下全部未成功设备）
     */
    WallpaperTaskDetailVO retry(String taskId, List<String> deviceIds);

    /**
     * 读取已转码文件（.bin 或 .png 缩略图），文件名需为 32 位 md5 + 扩展名
     */
    byte[] download(String fileName);
}
