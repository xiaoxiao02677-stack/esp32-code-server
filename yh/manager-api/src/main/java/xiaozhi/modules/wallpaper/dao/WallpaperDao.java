package xiaozhi.modules.wallpaper.dao;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import xiaozhi.modules.wallpaper.entity.WallpaperEntity;

@Mapper
public interface WallpaperDao extends BaseMapper<WallpaperEntity> {
}
