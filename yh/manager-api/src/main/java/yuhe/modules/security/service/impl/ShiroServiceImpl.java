package yuhe.modules.security.service.impl;

import java.util.List;

import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import yuhe.modules.security.dao.SysUserTokenDao;
import yuhe.modules.security.entity.SysUserTokenEntity;
import yuhe.modules.security.service.ShiroService;
import yuhe.modules.sys.dao.SysUserDao;
import yuhe.modules.sys.dao.SysUserRoleDao;
import yuhe.modules.sys.entity.SysUserEntity;

@AllArgsConstructor
@Service
public class ShiroServiceImpl implements ShiroService {
    private final SysUserDao sysUserDao;
    private final SysUserTokenDao sysUserTokenDao;
    private final SysUserRoleDao sysUserRoleDao;

    @Override
    public SysUserTokenEntity getByToken(String token) {
        return sysUserTokenDao.getByToken(token);
    }

    @Override
    public SysUserEntity getUser(Long userId) {
        return sysUserDao.selectById(userId);
    }

    @Override
    public List<String> getRoleCodes(Long userId) {
        return sysUserRoleDao.selectRoleCodesByUserId(userId);
    }
}
