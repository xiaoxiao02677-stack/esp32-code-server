<template>
  <div class="welcome" @keyup.enter="retrievePassword">
    <!-- kawaii 背景装饰：漂浮圆点（纯 CSS，见 auth.scss .auth-dots） -->
    <div class="auth-dots" aria-hidden="true"></div>
    <el-container style="height: 100%;">
      <!-- 保持相同的头部 -->
      <el-header>
        <div class="auth-header-inner">
          <img loading="lazy" alt="" class="header-logo" src="@/assets/kawaii/logo-kawaii.svg" />
          <img loading="lazy" alt="" :src="xiaozhiAiIcon" class="header-title-img" />
        </div>
      </el-header>
      <el-main>
        <form @submit.prevent="retrievePassword">
          <div class="login-box kawaii-jelly-enter">
            <!-- 修改标题部分 -->
            <div class="login-title-row">
              <i class="el-icon-cherry title-icon" aria-hidden="true"></i>
              <div class="login-text">{{ $t('retrievePassword.title') }}</div>
              <div class="login-welcome">
                {{ $t('retrievePassword.subtitle') }}
              </div>
            </div>

            <div class="login-form">
              <!-- 手机号输入 -->
              <div class="input-box">
                <div class="mobile-input-row">
                  <el-select v-model="form.areaCode" class="area-select">
                    <el-option v-for="item in mobileAreaList" :key="item.key" :label="`${item.name} (${item.key})`"
                      :value="item.key" />
                  </el-select>
                  <el-input v-model="form.mobile" :placeholder="$t('retrievePassword.mobilePlaceholder')" />
                </div>
              </div>

              <div class="captcha-row">
                <div class="input-box captcha-input-box">
                  <i class="el-icon-s-check input-icon" aria-hidden="true"></i>
                  <el-input v-model="form.captcha" :placeholder="$t('retrievePassword.captchaPlaceholder')"
                    class="captcha-input" />
                </div>
                <img loading="lazy" v-if="captchaUrl" :src="captchaUrl" alt="验证码" class="captcha-img"
                  @click="fetchCaptcha" />
              </div>

              <!-- 手机验证码 -->
              <div class="captcha-row">
                <div class="input-box captcha-input-box">
                  <i class="el-icon-message input-icon" aria-hidden="true"></i>
                  <el-input v-model="form.mobileCaptcha" :placeholder="$t('retrievePassword.mobileCaptchaPlaceholder')"
                    class="captcha-input" maxlength="6" />
                </div>
                <el-button type="primary" class="send-captcha-btn" :disabled="!canSendMobileCaptcha"
                  @click="sendMobileCaptcha">
                  <span>
                    {{ countdown > 0 ? `${countdown}${$t('register.secondsLater')}` : $t('retrievePassword.getMobileCaptcha') }}
                  </span>
                </el-button>
              </div>

              <!-- 新密码 -->
              <div class="input-box">
                <i class="el-icon-lock input-icon" aria-hidden="true"></i>
                <el-input v-model="form.newPassword" :placeholder="$t('retrievePassword.newPasswordPlaceholder')"
                  type="password" show-password />
              </div>

              <!-- 确认新密码 -->
              <div class="input-box">
                <i class="el-icon-key input-icon" aria-hidden="true"></i>
                <el-input v-model="form.confirmPassword" :placeholder="$t('retrievePassword.confirmNewPasswordPlaceholder')"
                  type="password" show-password />
              </div>

              <!-- 修改底部链接 -->
              <div class="link-row link-row--single">
                <div class="link-item" @click="goToLogin">{{ $t('retrievePassword.goToLogin') }}</div>
              </div>
            </div>

            <!-- 修改按钮文本 -->
            <div class="login-btn" @click="retrievePassword">{{ $t('retrievePassword.resetButton') }}</div>

            <!-- 保持相同的协议声明 -->
            <div class="agree-row">
              {{ $t('retrievePassword.agreeTo') }}
              <div class="agree-link" @click="openPage('/user-agreement.html')">{{ $t('register.userAgreement') }}</div>
              {{ $t('login.and') }}
              <div class="agree-link" @click="openPage('/privacy-policy.html')">{{ $t('register.privacyPolicy') }}</div>
            </div>
          </div>
        </form>
      </el-main>

      <!-- 保持相同的页脚 -->
      <el-footer>
        <version-footer />
      </el-footer>
    </el-container>
  </div>
</template>

<script>
import Api from '@/apis/api';
import VersionFooter from '@/components/VersionFooter.vue';
import { getUUID, goToPage, showDanger, showSuccess, validateMobile, sm2Encrypt } from '@/utils';
import { mapState } from 'vuex';
import i18n from '@/i18n';

// 导入语言切换功能
import { changeLanguage } from '@/i18n';

export default {
  name: 'retrieve',
  components: {
    VersionFooter
  },
  computed: {
    ...mapState({
      allowUserRegister: state => state.pubConfig.allowUserRegister,
      mobileAreaList: state => state.pubConfig.mobileAreaList,
      sm2PublicKey: state => state.pubConfig.sm2PublicKey
    }),
    // 获取当前语言
    currentLanguage() {
      return i18n.locale || "zh_CN";
    },
    // 根据当前语言获取对应的xiaozhi-ai图标
    xiaozhiAiIcon() {
      const currentLang = this.currentLanguage;
      switch (currentLang) {
        case "zh_CN":
          return require("@/assets/xiaozhi-ai.png");
        case "zh_TW":
          return require("@/assets/xiaozhi-ai_zh_TW.png");
        case "en":
          return require("@/assets/xiaozhi-ai_en.png");
        case "de":
          return require("@/assets/xiaozhi-ai_de.png");
        case "vi":
          return require("@/assets/xiaozhi-ai_vi.png");
        case "pt_BR":
          return require("@/assets/xiaozhi-ai_en.png");
        default:
          return require("@/assets/xiaozhi-ai.png");
      }
    },
    canSendMobileCaptcha() {
      return this.countdown === 0 && validateMobile(this.form.mobile, this.form.areaCode);
    }
  },
  data() {
    return {
      form: {
        areaCode: '+86',
        mobile: '',
        captcha: '',
        captchaId: '',
        mobileCaptcha: '',
        newPassword: '',
        confirmPassword: ''
      },
      captchaUrl: '',
      countdown: 0,
      timer: null
    }
  },
  mounted() {
    this.fetchCaptcha();
  },
  methods: {
    openPage(url) {
      const lang = this.$i18n ? this.$i18n.locale : 'zh_CN';
      if (!lang.startsWith('zh')) {
        url = url.replace('.html', '-en.html');
      }
      window.open(url, '_blank');
    },
    // 复用验证码获取方法
    fetchCaptcha() {
      this.form.captchaId = getUUID();
      Api.user.getCaptcha(this.form.captchaId, (res) => {
        if (res.status === 200) {
          const blob = new Blob([res.data], { type: res.data.type });
          this.captchaUrl = URL.createObjectURL(blob);

        } else {
          console.error('验证码加载异常:', error);
          showDanger(this.$t('register.captchaLoadFailed'));
        }
      });
    },

    // 封装输入验证逻辑
    validateInput(input, message) {
      if (!input.trim()) {
        showDanger(message);
        return false;
      }
      return true;
    },

    // 发送手机验证码
    sendMobileCaptcha() {
      if (!validateMobile(this.form.mobile, this.form.areaCode)) {
        showDanger(this.$t('retrievePassword.inputCorrectMobile'));
        return;
      }

      // 验证图形验证码
      if (!this.validateInput(this.form.captcha, this.$t('retrievePassword.captchaRequired'))) {
        this.fetchCaptcha();
        return;
      }

      // 清除可能存在的旧定时器
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }

      // 开始倒计时
      this.countdown = 60;
      this.timer = setInterval(() => {
        if (this.countdown > 0) {
          this.countdown--;
        } else {
          clearInterval(this.timer);
          this.timer = null;
        }
      }, 1000);

      // 调用发送验证码接口
      Api.user.sendSmsVerification({
        phone: this.form.areaCode + this.form.mobile,
        captcha: this.form.captcha,
        captchaId: this.form.captchaId
      }, (res) => {
        showSuccess(this.$t('retrievePassword.captchaSendSuccess'));
      }, (err) => {
        showDanger(err.data.msg || this.$t('register.captchaSendFailed'));
        this.countdown = 0;
        this.fetchCaptcha();
      });
    },

    // 修改逻辑
    retrievePassword() {
      // 验证逻辑
      if (!validateMobile(this.form.mobile, this.form.areaCode)) {
        showDanger(this.$t('retrievePassword.inputCorrectMobile'));
        return;
      }
      if (!this.form.captcha) {
        showDanger(this.$t('retrievePassword.captchaRequired'));
        return;
      }
      if (!this.form.mobileCaptcha) {
        showDanger(this.$t('retrievePassword.mobileCaptchaRequired'));
        return;
      }
      if (this.form.newPassword !== this.form.confirmPassword) {
        showDanger(this.$t('retrievePassword.passwordsNotMatch'));
        return;
      }

      // 加密密码
      let encryptedPassword;
      try {
        // 拼接图形验证码和新密码进行加密
        const captchaAndPassword = this.form.captcha + this.form.newPassword;
        encryptedPassword = sm2Encrypt(this.sm2PublicKey, captchaAndPassword);
      } catch (error) {
        console.error("密码加密失败:", error);
        showDanger(this.$t('sm2.encryptionFailed'));
        return;
      }

      Api.user.retrievePassword({
        phone: this.form.areaCode + this.form.mobile,
        password: encryptedPassword,
        code: this.form.mobileCaptcha,
        captchaId: this.form.captchaId
      }, (res) => {
        showSuccess(this.$t('retrievePassword.passwordUpdateSuccess'));
        goToPage('/login');
      }, (err) => {
        showDanger(err.data.msg || this.$t('message.error'));
        if (err.data != null && err.data.msg != null && (err.data.msg.indexOf('图形验证码') > -1 || err.data.msg.indexOf('Captcha') > -1)) {
          this.fetchCaptcha()
        }
      });
    },

    goToLogin() {
      goToPage('/login')
    }
  },
  beforeDestroy() {
    if (this.timer) {
      clearInterval(this.timer);
    }
  }
}
</script>

<style lang="scss" scoped>
@import './auth.scss';

.send-captcha-btn {
  margin-right: -5px;
  min-width: 100px;
  height: 46px;
  line-height: 1;
  padding: 0 14px;
  box-sizing: border-box;
  border-radius: var(--kawaii-radius-full, 9999px);
  font-size: 13px;
  border: none;
  flex-shrink: 0;

  &:disabled {
    background: var(--kawaii-surface-3, #FFE3EA);
    border-color: transparent;
    color: var(--kawaii-text-secondary, #8F7C84);
    cursor: not-allowed;
    opacity: 0.8;
  }
}
</style>
