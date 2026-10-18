package yuhe.modules.sys.service.impl;

import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import yuhe.modules.security.oauth2.TokenGenerator;
import yuhe.modules.sys.service.TokenService;

@AllArgsConstructor
@Service
public class TokenServiceImpl implements TokenService {

    @Override
    public String createToken(long userId) {
        // 生成一个token
        String token = TokenGenerator.generateValue();
        return token;
    }
}
