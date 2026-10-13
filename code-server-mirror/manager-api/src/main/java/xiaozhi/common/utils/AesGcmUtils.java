package xiaozhi.common.utils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;

/**
 * AES-256-GCM 加解密工具（用户自定义模型 API 密钥存储专用）
 * <p>
 * 存储格式：base64(iv[12] + ciphertext + tag[16])，GCM 认证标签 128 位。
 * 密钥规范：UTF-8 字节长度恰为 32 时直接使用；不足或超长时用 SHA-256 派生 32 字节密钥。
 * 静态无状态，失败统一抛 RenException(ErrorCode.CRYPTO_ERROR)。
 * </p>
 */
public class AesGcmUtils {

    /** GCM 推荐 IV 长度 12 字节（96 位） */
    private static final int IV_LENGTH = 12;
    /** GCM 认证标签长度 128 位 */
    private static final int TAG_BIT_LENGTH = 128;
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final String AES = "AES";
    private static final String SHA_256 = "SHA-256";
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    /**
     * 加密
     *
     * @param plain 明文
     * @param key   密钥（原始字符串，内部归一化为 32 字节）
     * @return base64(iv[12] + ciphertext + tag)
     */
    public static String encrypt(String plain, String key) {
        try {
            byte[] keyBytes = normalizeKey(key);
            byte[] iv = new byte[IV_LENGTH];
            SECURE_RANDOM.nextBytes(iv);

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(keyBytes, AES), new GCMParameterSpec(TAG_BIT_LENGTH, iv));
            byte[] cipherBytes = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));

            // iv(12) + ciphertext+tag
            byte[] out = new byte[IV_LENGTH + cipherBytes.length];
            System.arraycopy(iv, 0, out, 0, IV_LENGTH);
            System.arraycopy(cipherBytes, 0, out, IV_LENGTH, cipherBytes.length);
            return Base64.getEncoder().encodeToString(out);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException(ErrorCode.CRYPTO_ERROR, e);
        }
    }

    /**
     * 解密
     *
     * @param cipher base64(iv[12] + ciphertext + tag)
     * @param key    密钥（与加密时一致）
     * @return 明文
     */
    public static String decrypt(String cipher, String key) {
        try {
            byte[] keyBytes = normalizeKey(key);
            byte[] in = Base64.getDecoder().decode(cipher);
            if (in.length <= IV_LENGTH) {
                throw new RenException(ErrorCode.CRYPTO_ERROR);
            }
            byte[] iv = Arrays.copyOfRange(in, 0, IV_LENGTH);
            byte[] cipherBytes = Arrays.copyOfRange(in, IV_LENGTH, in.length);

            Cipher c = Cipher.getInstance(TRANSFORMATION);
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(keyBytes, AES), new GCMParameterSpec(TAG_BIT_LENGTH, iv));
            byte[] plainBytes = c.doFinal(cipherBytes);
            return new String(plainBytes, StandardCharsets.UTF_8);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            // 含 AEADBadTagException（密钥错误/密文被篡改）
            throw new RenException(ErrorCode.CRYPTO_ERROR, e);
        }
    }

    /**
     * 掩码：前 4 字符 + ****，其余隐藏；不足 4 字符全部掩码
     *
     * @param plain 明文（如 API 密钥）
     * @return 掩码串，如 sk-1****；null/空串原样返回
     */
    public static String mask(String plain) {
        if (plain == null || plain.isEmpty()) {
            return plain;
        }
        if (plain.length() <= 4) {
            return "****";
        }
        return plain.substring(0, 4) + "****";
    }

    /**
     * 密钥归一化：恰 32 字节直接用；否则 SHA-256 派生 32 字节
     */
    private static byte[] normalizeKey(String key) {
        if (key == null || key.isEmpty()) {
            throw new RenException(ErrorCode.CRYPTO_ERROR);
        }
        byte[] raw = key.getBytes(StandardCharsets.UTF_8);
        if (raw.length == 32) {
            return raw;
        }
        try {
            return MessageDigest.getInstance(SHA_256).digest(raw);
        } catch (Exception e) {
            throw new RenException(ErrorCode.CRYPTO_ERROR, e);
        }
    }
}
