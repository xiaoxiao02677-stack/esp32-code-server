package yuhe.modules.correctword.dao;

import org.apache.ibatis.annotations.Mapper;

import yuhe.common.dao.BaseDao;
import yuhe.modules.correctword.entity.CorrectWordFileEntity;

@Mapper
public interface CorrectWordFileDao extends BaseDao<CorrectWordFileEntity> {
}
