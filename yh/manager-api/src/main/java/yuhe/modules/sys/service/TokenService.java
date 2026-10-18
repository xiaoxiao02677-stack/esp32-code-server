package yuhe.modules.sys.service;

public interface TokenService {
    /**
     * 生成token
     *
     * @param userId
     * @return
     */
    String createToken(long userId);
}
