package yuhe.modules.knowledge.dao;

import org.apache.ibatis.annotations.Mapper;
import yuhe.common.dao.BaseDao;
import yuhe.modules.knowledge.entity.DocumentEntity;

/**
 * 文档 DAO
 */
@Mapper
public interface DocumentDao extends BaseDao<DocumentEntity> {
}
