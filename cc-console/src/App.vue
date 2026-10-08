<template>
  <div>
    <div v-if="booting" class="boot-progress">
      <div class="progress-bar" style="max-width: 420px; margin: 0 auto;">
        <div class="progress-bar-fill" style="--sk-progress-duration: 300ms"></div>
      </div>
    </div>

    <div v-else-if="!token" class="login-wrap">
      <div class="kawaii-card login-card fade-in-up">
        <img class="login-logo" :src="logoUrl" alt="logo" />
        <h1 class="login-title">屿禾工坊</h1>
        <p class="login-sub">可视化 · 点点鼠标就能管</p>
        <div class="login-form">
          <div class="field"><label>用户名</label>
            <input v-model.trim="loginForm.username" class="cc-input" placeholder="用户名 / 手机号" @keyup.enter="doLogin" /></div>
          <div class="field"><label>密码</label>
            <input v-model.trim="loginForm.password" type="password" class="cc-input" placeholder="密码" @keyup.enter="doLogin" /></div>
          <div class="field captcha-row"><label>验证码</label>
            <input v-model.trim="loginForm.captcha" class="cc-input" placeholder="验证码" @keyup.enter="doLogin" />
            <img v-if="captchaSrc" :src="captchaSrc" class="captcha-img" title="点击刷新" @click="refreshCaptcha" /></div>
          <button class="kawaii-pill login-btn hover-glow" :disabled="loginLoading" @click="doLogin">{{ loginLoading ? '登录中…' : '登 录' }}</button>
          <p v-if="loginError" class="login-error">{{ loginError }}</p>
        </div>
      </div>
    </div>

    <div v-else class="shell" :class="{ 'shell--compact': compactMode }">
      <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>
      <aside class="kawaii-card sidebar slide-in-left" :class="{ 'is-open': sidebarOpen }">
        <div class="sidebar-head">
          <img :src="logoUrl" class="logo" alt="logo" />
          <div class="sidebar-title">屿禾工坊</div>
          <button class="kawaii-pill kawaii-pill--ghost compact-toggle" :title="compactMode ? '切换宽松' : '切换紧凑'" @click="compactMode = !compactMode">{{ compactMode ? '🗗' : '🗗' }}</button>
        </div>
        <nav class="module-list">
          <div v-for="group in menuGroups" :key="group.label" class="menu-group">
            <div class="menu-group-label">{{ group.label }}</div>
            <button v-for="m in group.items" :key="m.key"
              class="module-item hover-glow"
              :class="{ 'is-active': active === m.key }"
              @click="selectPage(m.key)">
              <span class="module-icon" :class="'module-icon--' + m.color">{{ m.icon }}</span>
              <span class="module-name">{{ m.zh }}</span>
            </button>
          </div>
        </nav>
        <button class="kawaii-pill kawaii-pill--ghost logout" @click="doLogout">退出登录</button>
        <div class="theme-picker">
          <span class="theme-picker-label">🎨 主题</span>
          <div class="theme-swatches">
            <button v-for="t in THEMES" :key="t.id" class="theme-swatch"
              :class="{ 'is-active': currentTheme === t.id }" :title="t.name"
              :style="{ background: t.dot }" @click="setTheme(t.id)"></button>
          </div>
        </div>
      </aside>
      <button class="hamburger" @click="sidebarOpen = true">☰</button>

      <main class="kawaii-card main fade-in-up">
        <div class="breadcrumb">{{ currentBreadcrumb }}</div>
        <!-- ============ 总览 ============ -->
        <section v-if="active === 'overview'" class="page">
          <h2 class="page-title">总览</h2>
          <p class="page-sub">你的小智设备与智能体一目了然</p>
          <div class="stat-grid">
            <div v-for="(s, i) in stats" :key="s.label" class="stat-card hover-glow stagger-item" :style="{ '--i': i }">
              <div class="stat-num">{{ s.value }}</div>
              <div class="stat-label">{{ s.label }}</div>
            </div>
          </div>
          <h3 class="section-title">最近会话</h3>
          <div v-if="recentSessions.length" class="sess-list">
            <div v-for="(s, i) in recentSessions" :key="s.sessionId" class="sess-item border-trace stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="sess-title">{{ s.title }}</div>
              <div class="sess-meta">{{ s.createdAt }} · {{ s.chatCount }} 条</div>
            </div>
          </div>
          <p v-else class="empty-hint">暂无会话，去跟设备说句话吧～</p>
        </section>

        <!-- ============ 智能体 ============ -->
        <section v-else-if="active === 'agents'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">智能体</h2><p class="page-sub">管理你的 AI 角色</p></div>
            <button class="kawaii-pill" @click="loadAgents">刷新</button>
          </div>
          <div v-if="agents.length" class="agent-grid">
            <div v-for="(a, i) in agents" :key="a.id" class="agent-card hover-glow stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="agent-name">{{ a.agentName || '未命名' }}</div>
              <div class="agent-meta">LLM：{{ a.llmModelName || '-' }}</div>
              <div class="agent-meta">声音：{{ a.ttsVoiceName || '-' }}（{{ a.ttsModelName || '-' }}）</div>
              <div class="agent-meta">记忆：{{ a.memModelId || '-' }}</div>
              <div class="agent-actions">
                <button class="kawaii-pill kawaii-pill--ghost" @click="openChat(a)">查看聊天</button>
                <button class="kawaii-pill" @click="openAgentEdit(a)">编辑</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-del" @click="deleteAgent(a)">删除</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">还没有智能体，点「新建智能体」创建第一个</p>
          <button class="kawaii-pill create-btn hover-glow" @click="createAgent">＋ 新建智能体</button>

          <!-- 智能体编辑器模态 -->
          <div v-if="editAgent" class="modal-mask" @click.self="editAgent = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">{{ editAgent.id ? '编辑智能体' : '新建智能体' }}</h3>
              <div class="edit-grid">
                <div class="field"><label>名字</label>
                  <input v-model.trim="editForm.agentName" class="cc-input" placeholder="给 AI 起个名字" /></div>
                <div class="field"><label>大脑（LLM）</label>
                  <select v-model="editForm.llmModelId" class="cc-input">
                    <option v-for="m in modelOptions.LLM" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                  </select></div>
                <div class="field"><label>声音引擎（TTS）</label>
                  <select v-model="editForm.ttsModelId" class="cc-input" @change="loadEditVoices">
                    <option v-for="m in modelOptions.TTS" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                  </select></div>
                <div class="field"><label>音色</label>
                  <select v-model="editForm.ttsVoiceId" class="cc-input">
                    <option v-for="v in editVoices" :key="v.id" :value="v.id">{{ v.name }}</option>
                  </select></div>
                <div class="field"><label>记忆</label>
                  <select v-model="editForm.memModelId" class="cc-input">
                    <option v-for="m in modelOptions.Memory" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                  </select>
                  <p class="field-hint" v-if="memModelHint">{{ memModelHint }}</p></div>
                <div class="field"><label>意图配置</label>
                  <select v-model="editForm.intentModelId" class="cc-input">
                    <option v-for="m in modelOptions.Intent" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                  </select>
                  <p class="field-hint" v-if="intentModelHint">{{ intentModelHint }}</p></div>
                <div class="field"><label>语音识别（ASR）</label>
                  <select v-model="editForm.asrModelId" class="cc-input">
                    <option v-for="m in modelOptions.ASR" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                  </select></div>
                <div class="field"><label>聊天上报</label>
                  <select v-model.number="editForm.chatHistoryConf" class="cc-input">
                    <option :value="0">不上报</option>
                    <option :value="1">仅文字</option>
                    <option :value="2">文字+音频</option>
                  </select></div>
                <div class="field"><label>语速 (-50~100)</label>
                  <input v-model.number="editForm.ttsRate" type="number" class="cc-input" placeholder="0" /></div>
              </div>
              <div class="field"><label>人设提示词（小智怎么说话）</label>
                <textarea v-model="editForm.systemPrompt" class="cc-textarea" rows="5" placeholder="比如：你是温柔可爱的助手，说话简短口语化"></textarea></div>

              <!-- 设备绑定（原控制台逻辑：保存后设备需绑定此智能体才能对话） -->
              <div class="panel-box agent-bind-box">
                <div class="panel-label">📱 设备绑定（保存后配置生效）</div>
                <!-- 未绑定：引导绑定 -->
                <p v-if="!agentBoundDevices.length" class="page-sub bind-empty-tip" style="margin:6px 0 10px;">
                  ⚠️ 该智能体还没有绑定任何设备，设备将无法使用它对话。请在下方输入设备屏幕显示的 6 位验证码完成绑定。
                </p>
                <!-- 已绑定：原位置显示设备清单（型号+MAC） -->
                <div v-else class="bound-device-list">
                  <div class="panel-label" style="margin-top:6px;">✅ 已绑定设备（{{ agentBoundDevices.length }}）</div>
                  <div v-for="d in agentBoundDevices" :key="d.id || d.macAddress" class="bound-device-item">
                    <span class="bound-device-name">{{ d.alias || '智能体设备' }}</span>
                    <span class="bound-device-meta">{{ [d.deviceType, d.appVersion, d.macAddress].filter(Boolean).join(' · ') }}</span>
                    <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="unbindAgentDevice(d)">解绑</button>
                  </div>
                </div>
                <div class="bind-code-row">
                  <input v-model.trim="agentBindCode" class="cc-input bind-code-input" placeholder="设备上的 6 位验证码" maxlength="6" inputmode="numeric" @keyup.enter="bindDeviceByCode" />
                  <button class="kawaii-pill" :disabled="!(/^\d{6}$/.test(agentBindCode) && (editAgent && editAgent.id)) || agentBindBusy" @click="bindDeviceByCode">{{ agentBindBusy ? '绑定中…' : (editAgent && editAgent.id ? '验证码绑定' : '先保存智能体再绑定') }}</button>
                </div>
                <details class="manual-add-details">
                  <summary>手动录入 MAC 添加设备</summary>
                  <div class="edit-grid" style="margin-top:10px;">
                    <div class="field"><label>板型</label>
                      <input v-model.trim="manualDeviceForm.board" class="cc-input" placeholder="如 my-s3-tft（可空）" /></div>
                    <div class="field"><label>固件版本</label>
                      <input v-model.trim="manualDeviceForm.appVersion" class="cc-input" placeholder="如 2.5.1（可空）" /></div>
                    <div class="field"><label>MAC 地址 *</label>
                      <input v-model.trim="manualDeviceForm.macAddress" class="cc-input" placeholder="14:c1:9f:xx:xx:xx" /></div>
                  </div>
                  <button class="kawaii-pill" :disabled="!manualDeviceForm.macAddress || agentBindBusy" @click="manualAddDevice">{{ agentBindBusy ? '添加中…' : '＋ 手动添加设备' }}</button>
                </details>
              </div>

              <div class="modal-actions">
                <button class="kawaii-pill kawaii-pill--ghost" @click="editAgent = null">取消</button>
                <button class="kawaii-pill" @click="saveAgent">保存</button>
              </div>
            </div>
          </div>
        </section>

        <!-- ============ 音色试听 ============ -->
        <section v-else-if="active === 'voices'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">音色管理</h2><p class="page-sub">选一个 TTS 引擎，试听 / 新增 / 编辑音色（{{ voices.length }} 个）</p></div>
            <div class="chat-agent-picker">
              <select v-model="voiceTtsModel" class="cc-input select" @change="loadVoices">
                <option v-for="m in ttsModels" :key="m.id" :value="m.id">{{ m.modelName }}</option>
              </select>
              <button class="kawaii-pill" @click="openVoiceEdit(null)">＋ 新增音色</button>
            </div>
          </div>
          <div v-if="voices.length" class="voice-list">
            <div v-for="(v, i) in voices" :key="v.id" class="voice-item border-trace stagger-item" :style="{ '--i': Math.min(i, 12) }">
              <div class="voice-name">{{ v.name }}{{ v.dynamicInstruction ? ' 🔄动态' : '' }}</div>
              <div class="voice-lang">{{ v.languages || '—' }}</div>
              <div v-if="v.voiceInstruction" class="voice-lang" style="font-size:11px;color:#888;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">💬 {{ v.voiceInstruction }}</div>
              <div class="voice-actions">
                <button class="kawaii-pill kawaii-pill--ghost play-btn" :disabled="playingVoice === v.id" @click="playVoice(v)">
                  {{ playingVoice === v.id ? '试听中…' : '▶ 试听' }}
                </button>
                <button class="kawaii-pill kawaii-pill--ghost play-btn" @click="openVoiceEdit(v)">✎</button>
                <button class="kawaii-pill kawaii-pill--ghost play-btn danger" @click="deleteVoice(v)">🗑</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">该引擎暂无音色</p>
        </section>

        <!-- ============ 聊天记录 ============ -->
        <section v-else-if="active === 'chat'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">聊天记录</h2><p class="page-sub">点进会话查看对话（带语音回放）</p></div>
            <div class="chat-agent-picker">
              <select v-model="chatAgentId" class="cc-input select" @change="reloadChatSessions">
                <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
              </select>
              <button class="kawaii-pill" @click="reloadChatSessions">刷新</button>
            </div>
          </div>
          <div v-if="chatSessions.length" class="sess-list">
            <div v-for="(s, i) in chatSessions" :key="s.sessionId" class="sess-item border-trace stagger-item" :style="{ '--i': Math.min(i, 10) }"
              :class="{ 'is-active': chatSessionId === s.sessionId }" @click="loadChatHistory(s.sessionId)">
              <div class="sess-row">
                <div class="sess-main">
                  <div class="sess-title">{{ s.title }}</div>
                  <div class="sess-meta">{{ s.createdAt }} · {{ s.chatCount }} 条</div>
                </div>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click.stop="deleteChatSession(s)">🗑</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">该智能体还没有会话</p>
          <div v-if="chatHistory.length" class="chat-thread fade-in-up">
            <div v-for="(m, i) in chatHistory" :key="i" class="chat-bubble" :class="m.chatType === 1 ? 'chat-user' : 'chat-ai'">
              <div class="chat-text">{{ parseChatText(m.content) }}</div>
              <button v-if="m.audioId" class="chat-play" @click="playChatAudio(m.audioId)">▶ 播放语音</button>
            </div>
          </div>
        </section>


        <!-- ============ 记忆管理 ============ -->
        <section v-else-if="active === 'memory'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">记忆管理</h2><p class="page-sub">小智记住的关于你的事，可以修改、点赞或删除</p></div>
            <button class="kawaii-pill" @click="loadMemoryAgents">刷新</button>
          </div>

          <!-- 记忆引擎配置（mem_hybrid：短期总结+长期库+LLM沉淀） -->
          <div class="panel-box">
            <div class="panel-label">🧠 记忆引擎（{{ memoryAgents.length }} 个智能体使用中）</div>
            <div class="edit-grid" style="margin-top:10px;">
              <div class="field"><label>引擎</label>
                <select v-model="memoryEngine" class="cc-input" @change="onMemoryEngineChange">
                  <option v-for="m in modelOptions.Memory" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                </select>
                <p class="field-hint">{{ memoryEngineHint }}</p></div>
              <div class="field" v-if="memoryEngine === 'Memory_mem_hybrid' || memoryEngine === 'Memory_mem_local_short'">
                <label>总结 LLM（记忆压缩/事实沉淀用）</label>
                <select v-model="memorySummaryLlm" class="cc-input" :disabled="!memoryEngineAgentId">
                  <option value="">跟随主 LLM</option>
                  <option v-for="m in modelOptions.LLM" :key="m.id" :value="m.id">{{ m.modelName }}</option>
                </select>
                <p class="field-hint">独立于对话主脑：选便宜的模型做总结更省 token</p></div>
            </div>
            <div class="bind-code-row" style="margin-top:8px;">
              <select v-model="memoryEngineAgentId" class="cc-input bind-code-input" style="max-width:220px;">
                <option value="">应用到智能体…</option>
                <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
              </select>
              <button class="kawaii-pill" :disabled="!memoryEngineAgentId || !memoryEngine || memoryEngineSaving" @click="applyMemoryEngine">
                {{ memoryEngineSaving ? '应用中…' : '应用引擎配置' }}
              </button>
            </div>
            <p class="field-hint" v-if="memoryEngineApplied" style="color:var(--primary-strong);">{{ memoryEngineApplied }}</p>
          </div>

          <div class="panel-box">
            <div class="panel-label">智能体</div>
            <div class="mem-agent-row">
              <button v-for="ma in memoryAgents" :key="ma.agent_id"
                class="kawaii-pill mem-agent-btn" :class="{ 'is-on': memoryAgentId === ma.agent_id }"
                @click="selectMemAgent(ma.agent_id)">
                {{ ma.name }}（{{ ma.fact_count }}条）
              </button>
            </div>
          </div>

          <div class="mem-toolbar">
            <select v-model="memFilterCategory" class="cc-input select" @change="loadMemoryFacts">
              <option value="">全部分类</option>
              <option value="preference">偏好</option>
              <option value="profile">画像</option>
              <option value="habit">习惯</option>
              <option value="event">事件</option>
              <option value="general">通用</option>
            </select>
            <select v-model="memFilterStatus" class="cc-input select" @change="loadMemoryFacts">
              <option value="">全部状态</option>
              <option value="active">生效中</option>
              <option value="rejected">已驳回</option>
            </select>
            <div class="mem-view-switch">
              <button class="kawaii-pill mem-view-btn" :class="{ 'is-on': memViewMode === 'list' }" @click="switchMemView('list')">☰ 列表</button>
              <button class="kawaii-pill mem-view-btn" :class="{ 'is-on': memViewMode === 'timeline' }" @click="switchMemView('timeline')">🕐 时间轴</button>
              <button class="kawaii-pill mem-view-btn" :class="{ 'is-on': memViewMode === 'graph' }" @click="switchMemView('graph')">🕸 实体图谱</button>
            </div>
          </div>

          <!-- 时间轴视图（原控制台 MemoryTimeline 移植） -->
          <div v-if="memViewMode === 'timeline'" class="mem-timeline-wrap">
            <div class="mem-timeline-track">
              <div v-for="(group, gi) in memTimelineGroups" :key="group.date" class="mem-tl-group">
                <div class="mem-tl-date">
                  <span class="mem-tl-date-dot"></span>
                  <span class="mem-tl-date-text">{{ group.date }}</span>
                  <span class="mem-tl-date-count">{{ group.items.length }}</span>
                </div>
                <div class="mem-tl-items">
                  <div v-for="f in group.items" :key="f.fact_id" class="mem-tl-item" :class="'mem-tl-item--' + (f.category || 'general')">
                    <div class="mem-tl-item-head">
                      <span class="mem-tl-cat">{{ catZh(f.category) }}</span>
                      <span class="mem-tl-time">{{ memTimeOf(f.created_at) }}</span>
                      <span v-if="f.trust_score !== undefined" class="mem-tl-trust" :style="memTrustStyle(f.trust_score)">{{ Number(f.trust_score).toFixed(2) }}</span>
                      <span v-if="f.retrieval_count" class="mem-tl-rc">↺{{ f.retrieval_count }}</span>
                    </div>
                    <div class="mem-tl-content">{{ f.content }}</div>
                  </div>
                </div>
              </div>
            </div>
            <p v-if="!memoryFacts.length" class="empty-hint">暂无记忆数据</p>
          </div>

          <!-- 实体图谱视图（Canvas 手绘，免 ECharts） -->
          <div v-else-if="memViewMode === 'graph'" class="mem-graph-wrap">
            <canvas ref="memGraphCanvas" class="mem-graph-canvas" width="900" height="560"></canvas>
            <div class="mem-graph-legend">
              <span class="legend-item"><i class="dot dot--entity"></i>实体</span>
              <span class="legend-item"><i class="dot dot--fact"></i>记忆</span>
              <span class="legend-item"><i class="dot dot--hot"></i>高频实体</span>
            </div>
            <p v-if="!memoryFacts.length" class="empty-hint">暂无记忆数据</p>
          </div>

          <div v-else-if="memoryFacts.length" class="fact-list">
            <div v-for="(f, i) in memoryFacts" :key="f.fact_id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 10) }">
              <div class="fact-top">
                <span class="fact-cat" :class="'fact-cat--' + f.category">{{ catZh(f.category) }}</span>
                <span v-if="f.status !== 'active'" class="fact-status">{{ f.status === 'rejected' ? '已驳回' : f.status }}</span>
                <span class="fact-date">{{ f.created_at }}</span>
              </div>
              <div class="fact-content">{{ f.content }}</div>
              <div class="fact-trust">
                <div class="trust-bar"><div class="trust-fill" :style="{ width: (f.trust_score * 100) + '%' }"></div></div>
                <span class="trust-num">信任 {{ f.trust_score.toFixed(2) }}</span>
              </div>
              <div class="fact-actions">
                <button class="kawaii-pill fact-btn" @click="factFeedback(f, true)">👍 有用</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn" @click="factFeedback(f, false)">👎 没用</button>
                <button v-if="f.status !== 'active'" class="kawaii-pill fact-btn" @click="factReview(f, 'approve')">✓ 通过</button>
                <button v-else class="kawaii-pill kawaii-pill--ghost fact-btn" @click="factReview(f, 'reject')">✕ 驳回</button>
                <button class="kawaii-pill fact-btn" @click="openFactEdit(f)">✎ 编辑</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="factDelete(f)">🗑 删除</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">还没有记忆，多跟小智聊聊，它会自动记住你的喜好</p>

          <!-- 记忆编辑模态 -->
          <div v-if="editFact" class="modal-mask" @click.self="editFact = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">编辑记忆</h3>
              <p class="page-sub">内容变更会触发实体重抽取</p>
              <div class="field"><label>内容</label>
                <textarea v-model.trim="editFactForm.content" class="cc-textarea" rows="4" placeholder="记忆内容" maxlength="500"></textarea></div>
              <div class="field"><label>分类</label>
                <select v-model="editFactForm.category" class="cc-input">
                  <option value="preference">偏好</option>
                  <option value="profile">画像</option>
                  <option value="habit">习惯</option>
                  <option value="event">事件</option>
                  <option value="general">通用</option>
                </select></div>
              <div class="fact-actions">
                <button class="kawaii-pill" :disabled="!editFactForm.content" @click="saveFactEdit">保存</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="editFact = null">取消</button>
              </div>
            </div>
          </div>

          <div class="panel-box add-fact-box">
            <div class="panel-label">手动添加一条记忆</div>
            <div class="add-fact-row">
              <input v-model.trim="memNewFact" class="cc-input" placeholder="比如：我喜欢吃火锅" @keyup.enter="factCreate" />
              <button class="kawaii-pill" :disabled="!memNewFact || !memoryAgentId" @click="factCreate">添加</button>
            </div>
          </div>
        </section>

        <!-- ============ 模型管理 ============ -->
        <section v-else-if="active === 'models'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">模型管理</h2><p class="page-sub">全部模型类型配置 · 启停 · 一键测试可用性</p></div>
            <button class="kawaii-pill" @click="loadModelsByType">刷新</button>
          </div>

          <!-- 模型类型 tab（对齐原控制台 9 类） -->
          <div class="mem-toolbar model-type-tabs">
            <button v-for="t in MODEL_TYPES" :key="t.value"
              class="kawaii-pill mem-view-btn" :class="{ 'is-on': activeModelType === t.value }"
              @click="switchModelType(t.value)">{{ t.label }}{{ modelTypeCount(t.value) ? ` (${modelTypeCount(t.value)})` : '' }}</button>
            <button class="kawaii-pill create-btn" style="margin:0 0 0 auto;" @click="openModelEdit(null)">＋ 新增{{ activeModelType }}模型</button>
          </div>

          <div class="model-list">
            <div v-for="(m, i) in activeTypeModels" :key="m.id" class="model-item border-trace stagger-item" :style="{ '--i': Math.min(i, 10) }">
              <div class="model-main">
                <div class="model-name">{{ m.modelName }}</div>
                <div class="model-id">{{ m.id }}</div>
                <div v-if="testState[m.id]" class="model-test-result" :class="testState[m.id].ok === true ? 'test-ok' : (testState[m.id].ok === false ? 'test-fail' : '')">
                  {{ testState[m.id].text }}
                </div>
              </div>
              <div class="model-actions">
                <button class="kawaii-pill fact-btn" :disabled="testState[m.id] && testState[m.id].loading" @click="testModel(m)">
                  {{ testState[m.id] && testState[m.id].loading ? '测试中…' : '⚡ 一键测试' }}
                </button>
                <button class="kawaii-pill fact-btn" @click="openModelEdit(m)">✎ 编辑</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="deleteModelConfig(m)">🗑</button>
                <button class="switch" :class="{ on: m.isEnabled }" @click="toggleModel(m)" title="启用/停用">
                  <span class="switch-dot"></span>
                </button>
              </div>
            </div>
          </div>
          <p v-if="!activeTypeModels.length" class="empty-hint">该类型暂无模型，点右上「＋ 新增」创建</p>

          <!-- 模型新增/编辑模态（供应器动态表单 + 自定义接口） -->
          <div v-if="editModelCfg" class="modal-mask" @click.self="editModelCfg = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">{{ editModelCfg.id ? '编辑模型' : '新增 ' + activeModelType + ' 模型' }}</h3>
              <div class="edit-grid">
                <div class="field"><label>供应器</label>
                  <select v-model="editModelCfg.providerCode" class="cc-input" :disabled="!!editModelCfg.id" @change="onProviderChange">
                    <option v-for="p in modelProviders" :key="p.providerCode" :value="p.providerCode">{{ p.name }}</option>
                    <option value="__custom_openai__">⭐ 自定义接口（OpenAI 兼容）</option>
                  </select></div>
                <div class="field"><label>模型名称（显示）</label>
                  <input v-model.trim="editModelCfg.modelName" class="cc-input" placeholder="如 我的GPT" /></div>
                <div class="field" v-if="editModelCfg.providerCode === '__custom_openai__'"><label>provider type（内部）</label>
                  <input v-model.trim="editModelCfg.customType" class="cc-input" placeholder="openai" /></div>
              </div>
              <div class="field" v-if="providerFields.length" style="margin-top:8px;">
                <label>配置字段（{{ editModelCfg.providerCode === '__custom_openai__' ? '自定义接口字段' : '供应器要求' }}）</label>
                <div class="provider-fields">
                  <div v-for="f in providerFields" :key="f.key" class="provider-field-row">
                    <label class="pf-label">{{ f.label || f.key }}</label>
                    <input v-model.trim="editModelCfg.config[f.key]" class="cc-input" :type="f.type === 'password' ? 'password' : 'text'" :placeholder="f.placeholder || f.key" />
                    <button v-if="editModelCfg.providerCode === '__custom_openai__'" class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="removeCustomField(f.key)">✕</button>
                  </div>
                </div>
              </div>
              <div v-if="editModelCfg.providerCode === '__custom_openai__'" class="provider-field-row" style="margin-top:6px;">
                <input v-model.trim="newCustomFieldKey" class="cc-input" placeholder="新增字段名（如 api_key / base_url / model_name）" @keyup.enter="addCustomField" />
                <button class="kawaii-pill fact-btn" @click="addCustomField">＋ 加字段</button>
              </div>
              <div class="fact-actions" style="margin-top:14px;">
                <button class="kawaii-pill" :disabled="!editModelCfg.modelName || modelSaving" @click="saveModelConfig">{{ modelSaving ? '保存中…' : '保存' }}</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="editModelCfg = null">取消</button>
              </div>
            </div>
          </div>

          <div class="panel-box fade-in-up">
            <div class="panel-label">当前默认 TTS</div>
            <div class="panel-value">{{ defaultTtsName }}</div>
          </div>
        </section>

        <!-- ============ 设备管理 ============ -->
        <section v-else-if="active === 'devices'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">设备管理</h2><p class="page-sub">你的小智设备状态（改名/绑定/解绑）</p></div>
            <button class="kawaii-pill" @click="loadDevices">刷新</button>
          </div>
          <div v-if="devices.length" class="device-grid">
            <div v-for="(d, i) in devices" :key="d.id" class="device-card hover-glow stagger-item" :style="{ '--i': Math.min(i, 6) }">
              <div class="device-name">{{ d.alias || d.macAddress }}</div>
              <div class="device-meta">固件 {{ d.appVersion || '-' }} · {{ d.deviceType || '-' }}</div>
              <div class="device-meta">MAC {{ d.macAddress }}</div>
              <div class="device-meta">绑定：{{ d.bindUserName || '—' }}</div>
              <div class="device-actions">
                <button class="kawaii-pill fact-btn" @click="startDeviceRename(d)">✎ 改名</button>
                <button class="kawaii-pill fact-btn" @click="openDeviceBind(d)">⇄ 绑定</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="unbindDevice(d)">⤫ 解绑</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">没有设备</p>

          <!-- 设备改名模态 -->
          <div v-if="renameDevice" class="modal-mask" @click.self="renameDevice = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">设备改名</h3>
              <div class="field"><label>设备名称</label>
                <input v-model.trim="renameDeviceForm.alias" class="cc-input" placeholder="给我的小智起个名字" maxlength="40" /></div>
              <div class="fact-actions">
                <button class="kawaii-pill" :disabled="!renameDeviceForm.alias" @click="saveDeviceRename">保存</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="renameDevice = null">取消</button>
              </div>
            </div>
          </div>

          <!-- 设备绑定智能体模态 -->
          <div v-if="bindDevice" class="modal-mask" @click.self="bindDevice = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">绑定智能体</h3>
              <p class="page-sub">{{ bindDevice.alias || bindDevice.macAddress }} → 选择要绑定的智能体</p>
              <div class="field"><label>智能体</label>
                <select v-model="bindDeviceAgentId" class="cc-input">
                  <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
                </select></div>
              <div class="fact-actions">
                <button class="kawaii-pill" :disabled="!bindDeviceAgentId" @click="saveDeviceBind">绑定</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="bindDevice = null">取消</button>
              </div>
            </div>
          </div>
        </section>


        <!-- ============ 知识库 ============ -->
        <section v-else-if="active === 'knowledge'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">知识库</h2><p class="page-sub">给小智喂资料，让它懂你的领域知识</p></div>
            <button class="kawaii-pill" @click="loadDatasets">刷新</button>
          </div>
          <div class="panel-box add-fact-box">
            <div class="panel-label">新建知识库</div>
            <div class="add-fact-row">
              <input v-model.trim="newDatasetName" class="cc-input" placeholder="知识库名字，如：我的产品手册" @keyup.enter="createDataset" />
              <button class="kawaii-pill" :disabled="!newDatasetName" @click="createDataset">创建</button>
            </div>
          </div>
          <div v-if="datasets.length" class="fact-list">
            <div v-for="(d, i) in datasets" :key="d.id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="fact-top">
                <span class="fact-cat fact-cat--profile">📚 {{ d.name }}</span>
                <span class="fact-date">{{ d.createdAt || '' }}</span>
              </div>
              <div class="fact-content">文档 {{ d.documentCount || 0 }} 篇</div>
              <div class="fact-actions">
                <button class="kawaii-pill kawaii-pill--ghost fact-btn" @click="deleteDataset(d)">🗑 删除</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">还没有知识库</p>
        </section>

        <!-- ============ 系统参数 ============ -->
        <section v-else-if="active === 'params'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">系统参数</h2><p class="page-sub">服务器核心配置（改错会影响服务，谨慎操作）</p></div>
            <div class="search-inline"><input v-model.trim="paramFilter" class="cc-input cc-input--sm" placeholder="搜索参数编码…" /></div>
          </div>
          <div class="fact-list">
            <div v-for="(p, i) in filteredParams" :key="p.id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 10) }">
              <div class="fact-top">
                <span class="fact-cat fact-cat--event">{{ p.paramCode }}</span>
                <span class="fact-date">{{ p.remark || '' }}</span>
              </div>
              <div v-if="editParam && editParam.id === p.id" class="add-fact-row" style="margin: 8px 0;">
                <input v-model.trim="editParam.paramValue" class="cc-input" />
                <button class="kawaii-pill" @click="saveParam">保存</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="editParam = null">取消</button>
              </div>
              <template v-else>
                <div class="fact-content mono">{{ p.paramValue }}</div>
                <div class="fact-actions">
                  <button class="kawaii-pill fact-btn" @click="editParam = { ...p }">✎ 修改</button>
                </div>
              </template>
            </div>
          </div>
        </section>

        <!-- ============ 用户管理 ============ -->
        <section v-else-if="active === 'users'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">用户管理</h2><p class="page-sub">控制台注册用户</p></div>
            <button class="kawaii-pill" @click="loadUsers">刷新</button>
          </div>
          <div class="fact-list">
            <div v-for="(u, i) in users" :key="u.userid" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="fact-top">
                <span class="fact-cat fact-cat--preference">{{ u.mobile || u.userid }}</span>
                <span v-if="u.status === 0" class="fact-status">已禁用</span>
                <span class="fact-date">注册 {{ u.createDate }}</span>
              </div>
              <div class="fact-content">设备数：{{ u.deviceCount || 0 }}</div>
              <div class="fact-actions">
                <button class="kawaii-pill kawaii-pill--ghost fact-btn" @click="toggleUserStatus(u)">{{ u.status === 1 ? '禁用' : '启用' }}</button>
              </div>
            </div>
          </div>
          <p v-if="!users.length" class="empty-hint">暂无用户数据</p>
        </section>

        <!-- ============ 智能体模板 ============ -->
        <section v-else-if="active === 'templates'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">智能体模板</h2><p class="page-sub">一键套用的角色预设（{{ templates.length }} 个）</p></div>
            <button class="kawaii-pill" @click="loadTemplates">刷新</button>
          </div>
          <div class="agent-grid">
            <div v-for="(t, i) in templates" :key="t.id" class="agent-card hover-glow stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="agent-name">{{ t.agentName }}</div>
              <div class="agent-meta">编号：{{ t.agentCode || '—' }}</div>
              <div class="agent-meta">LLM：{{ t.llmModelId }}</div>
              <div class="agent-meta">TTS：{{ t.ttsModelId }}</div>
              <div class="agent-actions">
                <button class="kawaii-pill" @click="createAgentFromTemplate(t)">⚡ 用此模板创建智能体</button>
              </div>
            </div>
          </div>
          <p v-if="!templates.length" class="empty-hint">暂无模板</p>
        </section>

        <!-- ============ OTA 固件 ============ -->
        <section v-else-if="active === 'ota'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">OTA 固件</h2><p class="page-sub">设备固件版本管理（上传/删除）</p></div>
            <button class="kawaii-pill" @click="loadOta">刷新</button>
          </div>

          <div class="panel-box add-fact-box">
            <div class="panel-label">上传固件（.bin / .apk，仅超级管理员）</div>
            <div class="ota-upload-row">
              <input ref="otaFileInput" type="file" accept=".bin,.apk" class="cc-input" @change="onOtaFilePicked" />
              <button class="kawaii-pill" :disabled="!otaUploadFile || otaUploading" @click="uploadOta">
                {{ otaUploading ? '上传中…' : '⬆ 上传固件' }}
              </button>
            </div>
          </div>

          <div v-if="otaList.length" class="fact-list">
            <div v-for="(o, i) in otaList" :key="o.id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="fact-top">
                <span class="fact-cat fact-cat--habit">{{ o.firmwareType || o.id }}</span>
                <span class="fact-date">{{ o.createDate || '' }}</span>
              </div>
              <div class="fact-content">版本 {{ o.firmwareVersion || '—' }} · {{ o.memo || '' }}</div>
              <div class="fact-actions">
                <button v-if="o.downloadUrl" class="kawaii-pill fact-btn" @click="downloadOta(o)">⬇ 下载</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="deleteOta(o)">🗑 删除</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">暂无固件记录</p>
        </section>

        <!-- ============ 数据字典 ============ -->
        <section v-else-if="active === 'dicts'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">数据字典</h2><p class="page-sub">系统枚举值配置（增删改）</p></div>
            <button class="kawaii-pill" @click="loadDicts">刷新</button>
          </div>
          <div class="mem-toolbar">
            <select v-model="activeDictType" class="cc-input select" @change="loadDictData">
              <option value="">选择字典类型</option>
              <option v-for="t in dictTypes" :key="t.id" :value="t.dictType">{{ t.dictName }}</option>
            </select>
            <button class="kawaii-pill" :disabled="!activeDictType" @click="openDictEdit(null)">＋ 新增字典项</button>
          </div>
          <div v-if="dictData.length" class="fact-list">
            <div v-for="(d, i) in dictData" :key="d.id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 10) }">
              <div class="fact-top">
                <span class="fact-cat fact-cat--general">{{ d.dictLabel }}</span>
                <span class="fact-date">{{ d.remark || '' }}</span>
              </div>
              <div class="fact-content mono">{{ d.dictValue }}</div>
              <div class="fact-actions">
                <button class="kawaii-pill fact-btn" @click="openDictEdit(d)">✎ 编辑</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="deleteDictData(d)">🗑 删除</button>
              </div>
            </div>
          </div>
          <p v-else class="empty-hint">选择字典类型查看数据</p>

          <!-- 字典项编辑模态 -->
          <div v-if="editDictData" class="modal-mask" @click.self="editDictData = null">
            <div class="kawaii-card modal-card fade-in-up">
              <h3 class="modal-title">{{ editDictData.id ? '编辑字典项' : '新增字典项' }}</h3>
              <div class="edit-grid">
                <div class="field"><label>标签（显示名）</label>
                  <input v-model.trim="editDictData.dictLabel" class="cc-input" placeholder="如：启用" /></div>
                <div class="field"><label>值</label>
                  <input v-model.trim="editDictData.dictValue" class="cc-input" placeholder="如：1" /></div>
                <div class="field"><label>排序</label>
                  <input v-model.number="editDictData.sort" type="number" class="cc-input" placeholder="0" /></div>
                <div class="field"><label>备注</label>
                  <input v-model.trim="editDictData.remark" class="cc-input" placeholder="备注（可选）" /></div>
              </div>
              <div class="fact-actions">
                <button class="kawaii-pill" :disabled="!editDictData.dictLabel || editDictData.dictValue === ''" @click="saveDictData">保存</button>
                <button class="kawaii-pill kawaii-pill--ghost" @click="editDictData = null">取消</button>
              </div>
            </div>
          </div>
        </section>

        <!-- ============ 替换词 ============ -->
        <section v-else-if="active === 'correctwords'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">替换词</h2><p class="page-sub">让小智念对专有名词（写法|读法 每行一条）</p></div>
            <button class="kawaii-pill" @click="loadCorrectFiles">刷新</button>
          </div>
          <div v-if="editCorrect" class="panel-box">
            <div class="panel-label">{{ editCorrect.id ? '编辑' : '新建' }}替换词文件：{{ editCorrect.fileName }}</div>
            <input v-model.trim="editCorrect.fileName" class="cc-input" placeholder="文件名" style="margin: 8px 0;" />
            <textarea v-model="editCorrect.content" class="cc-textarea" rows="8" placeholder="小柚|小 yòu&#10;ESP32|易恩斯批三二"></textarea>
            <div class="fact-actions" style="margin-top: 10px;">
              <button class="kawaii-pill" @click="saveCorrectFile">保存</button>
              <button class="kawaii-pill kawaii-pill--ghost" @click="editCorrect = null">取消</button>
            </div>
          </div>
          <div v-if="correctFiles.length" class="fact-list">
            <div v-for="(f, i) in correctFiles" :key="f.id" class="fact-card border-trace stagger-item" :style="{ '--i': Math.min(i, 8) }">
              <div class="fact-top"><span class="fact-cat fact-cat--profile">✎ {{ f.fileName }}</span></div>
              <div class="fact-actions">
                <button class="kawaii-pill fact-btn" @click="editCorrect = { ...f }">✎ 编辑</button>
                <button class="kawaii-pill kawaii-pill--ghost fact-btn fact-del" @click="deleteCorrectFile(f)">🗑 删除</button>
              </div>
            </div>
          </div>
          <button class="kawaii-pill create-btn hover-glow" @click="editCorrect = { fileName: '', content: '' }">＋ 新建替换词文件</button>
        </section>

        <!-- ============ 服务器节点 ============ -->
        <section v-else-if="active === 'servers'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">服务器节点</h2><p class="page-sub">WebSocket 接入地址</p></div>
            <button class="kawaii-pill" @click="loadServers">刷新</button>
          </div>
          <div v-if="serverList.length" class="fact-list">
            <div v-for="(s, i) in serverList" :key="i" class="fact-card border-trace stagger-item" :style="{ '--i': i }">
              <div class="fact-content mono">{{ s }}</div>
            </div>
          </div>
          <p v-else class="empty-hint">暂无节点</p>
        </section>

        <!-- ============ MCP 接入点 ============ -->
        <section v-else-if="active === 'mcp'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">MCP 接入点</h2><p class="page-sub">查看智能体的 MCP 服务地址与工具列表</p></div>
            <button class="kawaii-pill" @click="loadMcpInfo">刷新</button>
          </div>
          <div class="mem-toolbar">
            <select v-model="mcpAgentId" class="cc-input select" @change="loadMcpInfo">
              <option value="">选择智能体</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
            </select>
            <button class="kawaii-pill" :disabled="!mcpAgentId || mcpTesting" @click="testMcp">
              {{ mcpTesting ? '测试中…' : '⚡ 一键测试' }}
            </button>
          </div>
          <div v-if="mcpTestResult" class="panel-box mcp-test-report" :class="mcpTestResult.ok ? 'mcp-test-ok' : 'mcp-test-fail'">
            <div class="panel-label">测试结果（{{ mcpTestResult.elapsed_ms }}ms）</div>
            <div class="panel-value">{{ mcpTestResult.ok ? '✅ ' : '❌ ' }}{{ mcpTestResult.message }}</div>
            <div v-if="mcpTestResult.address" class="page-sub mono">{{ mcpTestResult.address }}</div>
          </div>
          <template v-if="mcpAgentId">
            <div class="panel-box">
              <div class="panel-label">接入点地址</div>
              <div v-if="mcpAddress" class="mcp-address-row">
                <code class="fact-content mono mcp-address">{{ mcpAddress }}</code>
                <button class="kawaii-pill fact-btn" @click="copyMcpAddress">⧉ 复制</button>
              </div>
              <p v-else class="empty-hint">该智能体未配置 MCP 接入点</p>
            </div>
            <div class="panel-box">
              <div class="panel-label">工具列表（{{ mcpTools.length }}）</div>
              <div v-if="mcpTools.length" class="mcp-tool-grid">
                <div v-for="t in mcpTools" :key="t.name || t" class="mcp-tool-card border-trace">
                  <div class="mcp-tool-name">{{ t.name || t }}</div>
                  <div v-if="t.description" class="mcp-tool-desc">{{ t.description }}</div>
                </div>
              </div>
              <p v-else class="empty-hint">无工具（或未配置接入点）</p>
            </div>
          </template>
          <p v-else class="empty-hint">先选择一个智能体</p>
        </section>

        <!-- ============ 链路模拟器 ============ -->
        <section v-else-if="active === 'simulator'" class="page">
          <div class="page-head">
            <div><h2 class="page-title">链路模拟器</h2><p class="page-sub">ASR → LLM → TTS 全链路（浏览器替代硬件扬声器）</p></div>
          </div>
          <div class="mem-toolbar">
            <select v-model="simAgentId" class="cc-input select">
              <option value="">选择智能体</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.agentName }}</option>
            </select>
          </div>

          <!-- 阶段时间轴 -->
          <div class="sim-stages">
            <div class="sim-stage" :class="simStageClass('asr')">
              <div class="sim-stage-head">① ASR 语音识别</div>
              <div v-if="simStage.asr === 'done'" class="sim-stage-body">{{ simAsrText || '（无文本）' }}</div>
              <div v-else-if="simStage.asr === 'loading'" class="sim-stage-body sim-loading">识别中…</div>
              <div v-else class="sim-stage-body sim-hint">待输入</div>
            </div>
            <div class="sim-arrow">→</div>
            <div class="sim-stage" :class="simStageClass('llm')">
              <div class="sim-stage-head">② LLM 对话</div>
              <div v-if="simStage.llm === 'done'" class="sim-stage-body">{{ simLlmReply }}</div>
              <div v-else-if="simStage.llm === 'loading'" class="sim-stage-body sim-loading">思考中…</div>
              <div v-else-if="simStage.llm === 'error'" class="sim-stage-body sim-error">{{ simError.llm }}</div>
              <div v-else class="sim-stage-body sim-hint">待上一步</div>
            </div>
            <div class="sim-arrow">→</div>
            <div class="sim-stage" :class="simStageClass('tts')">
              <div class="sim-stage-head">③ TTS 合成播放</div>
              <div v-if="simStage.tts === 'done'" class="sim-stage-body">
                <audio ref="simAudioEl" controls :src="simAudioUrl"></audio>
                <a v-if="simAudioUrl" class="kawaii-pill kawaii-pill--ghost fact-btn" :href="simAudioUrl" download="sim-tts">⬇ 下载</a>
              </div>
              <div v-else-if="simStage.tts === 'loading'" class="sim-stage-body sim-loading">合成中…</div>
              <div v-else-if="simStage.tts === 'error'" class="sim-stage-body sim-error">{{ simError.tts }}</div>
              <div v-else class="sim-stage-body sim-hint">待上一步</div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="panel-box">
            <div class="panel-label">输入（说话 或 直接打字）</div>
            <div class="sim-input-row">
              <button class="kawaii-pill" :class="{ 'is-recording': simListening }" :disabled="!simAgentId" @click="toggleSimListen">
                {{ simListening ? '● 结束录音并发送识别' : '🎙 录音（服务端真实 ASR）' }}
              </button>
            </div>
            <div class="add-fact-row" style="margin-top:10px;">
              <input v-model.trim="simInputText" class="cc-input" placeholder="输入要发给小智的话（也可手动修改识别结果）" @keyup.enter="runSimPipeline" />
              <button class="kawaii-pill" :disabled="!simInputText || !simAgentId || simBusy" @click="runSimPipeline">
                {{ simBusy ? '链路运行中…' : '▶ 运行全链路' }}
              </button>
            </div>
            <p class="page-sub">TTS 试听上限 60 字；超长回复将截断合成。</p>
          </div>

          <!-- 日志 -->
          <div v-if="simLogs.length" class="panel-box">
            <div class="panel-label">链路日志</div>
            <pre class="sim-log">{{ simLogs.join('\n') }}</pre>
          </div>
        </section>

        <!-- ============ 高级（API 调试器） ============ -->
        <section v-else-if="active === 'apis'" class="page">
          <h2 class="page-title">API 调试（高级）</h2>
          <p class="page-sub">15 模块 142 个接口的原始调试面板，适合开发者</p>
          <div class="api-module-grid">
            <button v-for="(m, i) in apiModules" :key="m.key" class="api-module-card hover-glow stagger-item" :style="{ '--i': Math.min(i, 14) }"
              @click="selectApiModule(m.key)">
              <div class="api-module-name">{{ m.zh }}</div>
              <div class="api-module-count">{{ m.count }} 接口</div>
            </button>
          </div>
          <div v-if="activeApiModule" class="api-list fade-in-up">
            <div class="panel-box"><button class="kawaii-pill kawaii-pill--ghost" @click="activeApiModule = null">← 返回模块列表</button></div>
            <div v-for="(api, idx) in activeApis" :key="idx" class="api-item border-trace">
              <button class="api-row" @click="toggleApi(idx)">
                <span class="method" :class="'method--' + api.h.toLowerCase()">{{ api.h }}</span>
                <span class="api-path">{{ api.p }}</span>
                <span class="api-summary">{{ api.s }}</span>
              </button>
              <div v-if="openIdx === idx" class="api-panel">
                <textarea v-model="debugState[idx].query" class="cc-textarea" rows="2" placeholder='{"page":1}（JSON）'></textarea>
                <textarea v-model="debugState[idx].body" class="cc-textarea" rows="3" placeholder='Body（JSON）'></textarea>
                <button class="kawaii-pill send-btn" :disabled="debugState[idx].loading" @click="sendRequest(api, idx)">{{ debugState[idx].loading ? '请求中…' : '发送' }}</button>
                <pre class="response-box">{{ debugState[idx].result || '（尚未请求）' }}</pre>
              </div>
            </div>
          </div>
        </section>

        <!-- 音色新增/编辑模态（全局层：音色页/模型页均可弹出） -->
        <div v-if="editVoice" class="modal-mask" @click.self="editVoice = null">
          <div class="kawaii-card modal-card fade-in-up">
            <h3 class="modal-title">{{ editVoice.id ? '编辑音色' : '新增音色（' + (ttsModels.find(m => m.id === voiceTtsModel) || {}).modelName + '）' }}</h3>
            <div class="edit-grid">
              <div class="field"><label>音色名称 *</label>
                <input v-model.trim="editVoice.name" class="cc-input" placeholder="如 温柔小何" /></div>
              <div class="field"><label>音色代码 tts_voice *（合成用的 speaker，如 zh_female_xiaohe_uranus_bigtts / Cherry / S_xxx）</label>
                <input v-model.trim="editVoice.ttsVoice" class="cc-input" placeholder="音色 speaker 代码" /></div>
              <div class="field"><label>支持语言（如 普通话 / 英语、普通话）</label>
                <input v-model.trim="editVoice.languages" class="cc-input" placeholder="普通话" /></div>
              <div class="field"><label>排序（数字，小的在前）</label>
                <input v-model.number="editVoice.sort" type="number" class="cc-input" placeholder="0" /></div>
            </div>
            <div class="field" style="margin-top:8px;"><label>语气指令（doubao 2.0 音色生效，如「用标准大陆普通话说话」）</label>
              <input v-model.trim="editVoice.voiceInstruction" class="cc-input" placeholder="可选" /></div>
            <div class="field" style="margin-top:8px;">
              <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                <input type="checkbox" v-model="editVoice.dynamicInstruction" /> ✔ 动态更新
              </label>
              <p class="field-hint">勾选后由 LLM 读取短期+长期聊天记录，自动定制口语化语气指令（覆盖固定指令）</p>
            </div>
            <div class="field" v-if="editVoice.dynamicInstruction" style="margin-top:8px;"><label>指令生成 LLM</label>
              <select v-model="editVoice.instructionLlmId" class="cc-input">
                <option value="">跟随智能体主 LLM</option>
                <option v-for="m in modelOptions.LLM" :key="m.id" :value="m.id">{{ m.modelName }}</option>
              </select></div>
            <div class="field" style="margin-top:8px;"><label>试听链接 voice_demo（可直接粘贴一个音频 URL）</label>
              <input v-model.trim="editVoice.voiceDemo" class="cc-input" placeholder="https://... 可选" /></div>
            <div class="fact-actions" style="margin-top:14px;">
              <button class="kawaii-pill" :disabled="!editVoice.name || !editVoice.ttsVoice || voiceSaving" @click="saveVoice">{{ voiceSaving ? '保存中…' : '保存' }}</button>
              <button class="kawaii-pill kawaii-pill--ghost" @click="editVoice = null">取消</button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script>
import { sm2 } from 'sm-crypto';
import API_CATALOG from './lib/apiCatalog';

const API_BASE = '/xiaozhi';

// 模型类型（对齐原控制台 ProviderManagement 的 9 类）
const MODEL_TYPES = [
  { value: 'TTS', label: '🔊 TTS 语音合成' },
  { value: 'LLM', label: '🧠 LLM 大语言' },
  { value: 'ASR', label: '🎙 ASR 语音识别' },
  { value: 'VLLM', label: '👁 VLLM 视觉' },
  { value: 'Intent', label: '🎯 Intent 意图' },
  { value: 'Memory', label: '💾 Memory 记忆' },
  { value: 'VAD', label: '〰 VAD 活动检测' },
  { value: 'Plugin', label: '🔌 Plugin 插件' },
  { value: 'RAG', label: '📚 RAG 知识库' },
];

export default {
  name: 'App',
  data() {
    return {
      MODEL_TYPES,
      logoUrl: `${import.meta.env.BASE_URL}logo.svg`,
      booting: true,
      token: '',
      pubKey: '',
      captchaUuid: '',
      captchaSrc: '',
      loginForm: { username: '', password: '', captcha: '' },
      loginLoading: false,
      loginError: '',
      active: 'overview',
      sidebarOpen: false,
      compactMode: false,
      // 主题
      THEMES: [
        { id: 'kawaii', name: '奶油粉（默认）', dot: 'linear-gradient(135deg,#F9A8D4,#A78BFA)' },
        { id: 'blue', name: '蓝白', dot: 'linear-gradient(135deg,#2563EB,#0EA5E9)' },
        { id: 'dark', name: '深色', dot: 'linear-gradient(135deg,#0B1120,#3B82F6)' },
        { id: 'purple', name: '紫色', dot: 'linear-gradient(135deg,#7C3AED,#C026D3)' },
        { id: 'green', name: '绿色', dot: 'linear-gradient(135deg,#16A34A,#84CC16)' },
        { id: 'morandi', name: '莫兰迪', dot: 'linear-gradient(135deg,#8B9DAF,#D8A7A0)' },
      ],
      currentTheme: 'kawaii',
      menuGroups: [
        { label: '概览', items: [
          { key: 'overview', zh: '总览', icon: '⌂', color: 'primary' },
        ]},
        { label: '智能体', items: [
          { key: 'agents', zh: '智能体', icon: '◈', color: 'primary' },
          { key: 'templates', zh: '智能体模板', icon: '📋', color: 'primary' },
          { key: 'mcp', zh: 'MCP 接入点', icon: '🔗', color: 'model' },
        ]},
        { label: '内容', items: [
          { key: 'memory', zh: '记忆管理', icon: '🧠', color: 'knowledge' },
          { key: 'knowledge', zh: '知识库', icon: '📚', color: 'knowledge' },
          { key: 'correctwords', zh: '替换词', icon: '✎', color: 'contact' },
        ]},
        { label: '音视', items: [
          { key: 'voices', zh: '音色试听', icon: '♪', color: 'voice' },
          { key: 'chat', zh: '聊天记录', icon: '💬', color: 'knowledge' },
        ]},
        { label: '系统', items: [
          { key: 'devices', zh: '设备管理', icon: '⚙', color: 'system' },
          { key: 'models', zh: '模型管理', icon: '◇', color: 'model' },
          { key: 'params', zh: '系统参数', icon: '🎛', color: 'system' },
          { key: 'users', zh: '用户管理', icon: '👥', color: 'system' },
          { key: 'ota', zh: 'OTA 固件', icon: '📦', color: 'system' },
          { key: 'dicts', zh: '数据字典', icon: '📖', color: 'system' },
          { key: 'servers', zh: '服务器节点', icon: '🖥', color: 'system' },
        ]},
        { label: '调试', items: [
          { key: 'simulator', zh: '链路模拟器', icon: '🧪', color: 'voice' },
          { key: 'apis', zh: 'API 调试（高级）', icon: '⌘', color: 'contact' },
        ]},
      ],
      stats: [
        { label: '智能体', value: 0 },
        { label: '设备', value: 0 },
        { label: '会话', value: 0 },
        { label: 'TTS 引擎', value: 0 },
      ],
      agents: [],
      recentSessions: [],
      ttsModels: [],
      defaultTtsName: '',
      voiceTtsModel: '',
      voices: [],
      playingVoice: '',
      chatSessions: [],
      chatSessionId: '',
      chatHistory: [],
      devices: [],
      memoryAgents: [],
      memoryAgentId: '',
      memoryFacts: [],
      memFilterCategory: '',
      memFilterStatus: '',
      memNewFact: '',
      memViewMode: 'list',
      activeApiModule: '',
      apiSearch: '',
      openApi: '',
      openIdx: null,
      debugState: {},
      audioEl: null,
      // 智能体编辑器
      editAgent: null,
      editForm: {},
      modelOptions: { LLM: [], TTS: [], Memory: [], ASR: [], VLLM: [], Intent: [] },
      editVoices: [],
      // 智能体编辑器-设备绑定
      agentBindCode: '',
      agentBindBusy: false,
      manualDeviceForm: { board: '', appVersion: '', macAddress: '' },
      agentBoundDevices: [],
      // 记忆引擎配置（mem_hybrid）
      memoryEngine: 'Memory_mem_hybrid',
      memorySummaryLlm: 'LLM_DeepSeek',
      memoryEngineAgentId: '',
      memoryEngineSaving: false,
      memoryEngineApplied: '',
      // 知识库
      datasets: [],
      newDatasetName: '',
      // 系统参数
      sysParams: [],
      paramFilter: '',
      editParam: null,
      // 用户
      users: [],
      // 模板
      templates: [],
      // OTA
      otaList: [],
      // 字典
      dictTypes: [],
      dictData: [],
      activeDictType: '',
      // 替换词
      correctFiles: [],
      editCorrect: null,
      // 服务器
      serverList: [],
      // 设备写操作
      renameDevice: null,
      renameDeviceForm: { alias: '' },
      bindDevice: null,
      bindDeviceAgentId: '',
      // 聊天
      chatAgentId: '',
      // 记忆编辑
      editFact: null,
      editFactForm: { content: '', category: 'general' },
      // 字典编辑
      editDictData: null,
      // OTA
      otaUploadFile: null,
      otaUploading: false,
      // MCP
      mcpAgentId: '',
      mcpAddress: '',
      mcpTools: [],
      mcpTesting: false,
      mcpTestResult: null,
      // 音色管理
      editVoice: null,
      voiceSaving: false,
      // 模型管理（9 类型 + 一键测试）
      activeModelType: 'TTS',
      modelsByType: {},
      testState: {},
      // 模型 CRUD
      modelProviders: [],
      editModelCfg: null,
      providerFields: [],
      newCustomFieldKey: '',
      modelSaving: false,
      // 链路模拟器
      simAgentId: '',
      simInputText: '',
      simAsrText: '',
      simLlmReply: '',
      simAudioUrl: '',
      simStage: { asr: '', llm: '', tts: '' },
      simError: { asr: '', llm: '', tts: '' },
      simLogs: [],
      simBusy: false,
      simListening: false,
      simRecorder: null,
      simAsrModelId: '',
    };
  },
  computed: {
    memoryEngineHint() {
      const map = {
        Memory_mem_hybrid: '⭐ 推荐：短期 LLM 滚动总结 + Holographic 长期事实库 + LLM 自动沉淀（隐式信息也能记住）',
        Memory_mem_holographic: '长期事实库（正则抽取，零 LLM 成本，只抓显式表达）',
        Memory_mem_local_short: '纯短期总结（LLM 压缩对话档案，无长期事实库）',
        Memory_mem_report_only: '仅上报聊天记录，不生成记忆',
        Memory_nomem: '完全关闭记忆',
        Memory_mem0ai: '需要 Mem0AI API Key（模型管理里配置后启用）',
        Memory_powermem: '需要 PowerMem 凭据（模型管理里配置后启用）',
      };
      return map[this.memoryEngine] || '';
    },
    memModelHint() {
      const id = this.editForm && this.editForm.memModelId;
      const map = {
        Memory_mem_holographic: '本地全息记忆：自动抽取事实/时间线/实体，功能最全',
        Memory_mem_local_short: '短期记忆：对话摘要总结，轻量省 token',
        Memory_mem_report_only: '仅上报聊天记录，不生成记忆',
        Memory_nomem: '完全关闭记忆',
        Memory_mem0ai: '需要 Mem0AI API Key（模型管理里配置后启用）',
        Memory_powermem: '需要 PowerMem 凭据（模型管理里配置后启用）',
      };
      return map[id] || '';
    },
    intentModelHint() {
      const id = this.editForm && this.editForm.intentModelId;
      const map = {
        Intent_function_call: '推荐：大模型自主决定何时调工具（音量/天气/音乐等）',
        Intent_intent_llm: '外挂专用小模型识别意图（省主模型 token）',
        Intent_nointent: '跳过意图识别；工具仍可用（LLM 原生 tool_calls）',
      };
      return map[id] || '';
    },
    apiModules() {
      return Object.keys(API_CATALOG).map((key) => ({
        key, zh: API_CATALOG[key].zh, count: API_CATALOG[key].apis.length,
      }));
    },
    activeApis() {
      return (API_CATALOG[this.activeApiModule] || {}).apis || [];
    },
    filteredParams() {
      const kw = this.paramFilter.toLowerCase();
      if (!kw) return this.sysParams;
      return this.sysParams.filter((p) => (p.paramCode || '').toLowerCase().includes(kw) || (p.remark || '').toLowerCase().includes(kw));
    },
    currentBreadcrumb() {
      for (const group of this.menuGroups) {
        const hit = group.items.find((m) => m.key === this.active);
        if (hit) return `${group.label} / ${hit.zh}`;
      }
      return '';
    },
    memTimelineGroups() {
      const map = new Map();
      (this.memoryFacts || []).forEach((f) => {
        const d = String(f.created_at || '').slice(0, 10) || '—';
        if (!map.has(d)) map.set(d, []);
        map.get(d).push(f);
      });
      return Array.from(map.entries())
        .sort((a, b) => (a[0] < b[0] ? 1 : -1))
        .map(([date, items]) => ({
          date,
          items: items.slice().sort((a, b) =>
            String(b.created_at || '').localeCompare(String(a.created_at || ''))),
        }));
    },
    activeTypeModels() {
      return this.modelsByType[this.activeModelType] || [];
    },
  },
  mounted() {
    setTimeout(() => { this.booting = false; }, 300);
    // 主题恢复（登录页也生效）
    const savedTheme = localStorage.getItem('cc_theme') || 'kawaii';
    this.currentTheme = savedTheme;
    document.documentElement.setAttribute('data-theme', savedTheme);
    this.token = localStorage.getItem('cc_token') || '';
    this.pubKey = localStorage.getItem('cc_pubkey') || '';
    if (!this.token) {
      this.fetchPubConfig();
    } else {
      this.loadAll();
    }
  },
  methods: {
    async api(path, opts = {}) {
      const headers = this.authHeaders();
      if (opts.json) {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.json);
      }
      if (opts.contentType) {
        // 二进制上传（Blob/ArrayBuffer）：显式声明 Content-Type
        headers['Content-Type'] = opts.contentType;
        opts.body = opts.rawBody;
      }
      const resp = await fetch(API_BASE + path, { method: opts.method || 'GET', headers, body: opts.body });
      // ===== 统一认证/错误拦截（FR-07/FR-08：401/403/500 不在各页面各自处理）=====
      if (resp.status === 401) {
        this.token = '';
        localStorage.removeItem('cc_token');
        alert('登录已过期，请重新登录');
        return { code: 401, msg: '登录已过期', data: null };
      }
      if (resp.status === 403) {
        return { code: 403, msg: '没有权限执行此操作（需要管理员角色）', data: null };
      }
      if (resp.status >= 500) {
        return { code: resp.status, msg: `服务器异常（HTTP ${resp.status}），请稍后重试`, data: null };
      }
      const ctype = resp.headers.get('Content-Type') || '';
      if (ctype.includes('audio') || ctype.includes('octet-stream')) return resp.blob();
      const text = await resp.text();
      try {
        const parsed = JSON.parse(text);
        // 二进制端点（ttsPreview 等）失败时返回 {code:500} JSON —— 转成异常，
        // 避免调用方把 JSON 对象当 Blob 用（createObjectURL 崩溃）
        if (parsed && typeof parsed === 'object' && parsed.code !== undefined && parsed.code !== 0
            && /ttsPreview|llmPreview|modelTest|asrRecognize|\/api\//.test(path)) {
          throw new Error(parsed.msg || ('错误码 ' + parsed.code));
        }
        return parsed;
      } catch (e) {
        if (e instanceof SyntaxError) return text;
        throw e;
      }
    },
    authHeaders() {
      const headers = {};
      let raw = this.token;
      try { raw = JSON.parse(raw).token; } catch (e) {}
      if (raw) headers.Authorization = 'Bearer ' + raw;
      return headers;
    },
    async loadAll() {
      await Promise.all([this.loadAgents(), this.loadTtsModels(), this.loadDevices()]);
    },
    async loadAgents() {
      const res = await this.api('/agent/list');
      this.agents = (res && res.code === 0 && res.data) || [];
      this.stats[0].value = this.agents.length;
      if (this.agents.length) await this.loadSessions(this.agents[0].id);
    },
    async loadSessions(agentId, isChat = false) {
      if (!agentId) return;
      const res = await this.api(`/agent/${agentId}/sessions?page=1&limit=10`);
      const list = (res && res.data && res.data.list) || [];
      this.stats[2].value = res && res.data ? res.data.total : 0;
      if (isChat) {
        this.chatSessions = list;
        this.chatSessionId = '';
        this.chatHistory = [];
      } else {
        this.recentSessions = list.slice(0, 5);
      }
    },
    async loadTtsModels() {
      const res = await this.api('/models/list?modelType=TTS&page=1&limit=50');
      const list = (res && res.data && res.data.list) || [];
      this.ttsModels = list;
      this.stats[3].value = list.length;
      const def = list.find((m) => m.isDefault);
      this.defaultTtsName = def ? def.modelName : '未设置';
      if (!this.voiceTtsModel && list.length) {
        this.voiceTtsModel = list[0].id;
        this.loadVoices();
      }
    },
    async loadVoices() {
      // voiceTtsModel 未就绪时先拉 TTS 模型列表并选默认（避免点击菜单无反应）
      if (!this.voiceTtsModel) {
        await this.loadTtsModels();
        if (!this.voiceTtsModel) {
          this.voices = [];
          return;
        }
      }
      const res = await this.api(`/models/${this.voiceTtsModel}/voices`);
      this.voices = (res && res.code === 0 && res.data) || [];
    },
    async playVoice(v) {
      this.playingVoice = v.id;
      try {
        const blob = await this.api(`/models/ttsPreview?modelId=${this.voiceTtsModel}&voice=${encodeURIComponent(v.ttsVoice || v.id)}`);
        this.playBlob(blob);
      } catch (e) {
        alert('试听失败：' + (e.message || '网络异常'));
      } finally {
        setTimeout(() => { this.playingVoice = ''; }, 1500);
      }
    },
    // ===== 音色 CRUD（后端 POST/PUT /ttsVoice） =====
    openVoiceEdit(v) {
      if (!this.voiceTtsModel) { alert('请先选择 TTS 引擎'); return; }
      this.loadModelOptions(); // 确保 LLM 下拉可用（动态指令生成用）
      this.editVoice = v
        ? { id: v.id, name: v.name || '', ttsVoice: v.ttsVoice || '', languages: v.languages || '', sort: v.sort != null ? v.sort : 0, voiceInstruction: v.voiceInstruction || '', voiceDemo: v.voiceDemo || '', dynamicInstruction: !!v.dynamicInstruction, instructionLlmId: v.instructionLlmId || '' }
        : { id: '', name: '', ttsVoice: '', languages: '普通话', sort: 0, voiceInstruction: '', voiceDemo: '', dynamicInstruction: false, instructionLlmId: '' };
    },
    async saveVoice() {
      const ev = this.editVoice;
      if (!ev || !ev.name || !ev.ttsVoice) { alert('名称与音色代码必填'); return; }
      this.voiceSaving = true;
      try {
        const payload = {
          name: ev.name, ttsVoice: ev.ttsVoice, ttsModelId: this.voiceTtsModel,
          languages: ev.languages || '普通话', sort: ev.sort || 0,
          voiceInstruction: ev.voiceInstruction || '', voiceDemo: ev.voiceDemo || '',
          dynamicInstruction: !!ev.dynamicInstruction,
          instructionLlmId: ev.dynamicInstruction ? (ev.instructionLlmId || null) : null,
        };
        const res = ev.id
          ? await this.api(`/ttsVoice/${ev.id}`, { method: 'PUT', json: payload })
          : await this.api('/ttsVoice', { method: 'POST', json: payload });
        if (res && res.code === 0) {
          this.editVoice = null;
          this.loadVoices();
          alert(ev.id ? '音色已更新' : '音色已添加，可在智能体里选用');
        } else {
          alert('保存失败：' + ((res && res.msg) || ''));
        }
      } catch (e) {
        alert('保存异常：' + (e.message || ''));
      } finally {
        this.voiceSaving = false;
      }
    },
    async deleteVoice(v) {
      if (!confirm(`删除音色「${v.name}」？`)) return;
      try {
        const res = await this.api('/ttsVoice/delete', { method: 'POST', json: [v.id] });
        if (res && res.code === 0) { this.loadVoices(); }
        else { alert('删除失败：' + ((res && res.msg) || '')); }
      } catch (e) {
        alert('删除异常：' + (e.message || ''));
      }
    },
    async loadChatHistory(sessionId) {
      this.chatSessionId = sessionId;
      const agentId = this.agents[0] && this.agents[0].id;
      if (!agentId) return;
      const res = await this.api(`/agent/${agentId}/chat-history/${sessionId}`);
      this.chatHistory = (res && res.code === 0 && res.data) || [];
    },
    parseChatText(content) {
      try {
        const obj = JSON.parse(content);
        return (obj.content || obj.text || content).toString();
      } catch (e) { return content; }
    },
    async playChatAudio(audioId) {
      try {
        const res = await this.api(`/agent/audio/${audioId}`, { method: 'POST' });
        const realId = res && res.data && res.data.data ? res.data.data : (res && res.data);
        const blob = await this.api(`/voiceClone/play/${realId}`);
        this.playBlob(blob);
      } catch (e) {
        alert('音频加载失败');
      }
    },
    playBlob(blob) {
      const url = URL.createObjectURL(blob);
      if (!this.audioEl) this.audioEl = new Audio();
      this.audioEl.src = url;
      this.audioEl.play().catch(() => alert('播放失败'));
      this.audioEl.onended = () => URL.revokeObjectURL(url);
    },
    async toggleModel(m) {
      const newStatus = m.isEnabled ? 0 : 1;
      const res = await this.api(`/models/enable/${m.id}/${newStatus}`, { method: 'PUT' });
      if (res && res.code === 0) {
        m.isEnabled = newStatus;
      } else {
        alert('操作失败：' + ((res && res.msg) || '请检查权限'));
      }
    },
    async loadDevices() {
      const agentId = this.agents[0] && this.agents[0].id;
      if (!agentId) return;
      const res = await this.api(`/device/bind/${agentId}`, { method: 'POST', json: {} });
      this.devices = (res && res.code === 0 && res.data) || [];
      this.stats[1].value = this.devices.length;
    },
    async loadAllDevices() {
      // 管理员视角全量设备列表（含未绑定）：契约端点 /admin/device/all（分页）
      // 失败则回退绑定视角 loadDevices()
      const res = await this.api('/admin/device/all?page=1&limit=200');
      if (res && res.code === 0 && res.data && Array.isArray(res.data.list)) {
        this.devices = res.data.list;
      } else {
        await this.loadDevices();
      }
    },
    startDeviceRename(d) {
      this.renameDevice = d;
      this.renameDeviceForm = { alias: d.alias || '' };
    },
    async saveDeviceRename() {
      if (!this.renameDeviceForm.alias) return;
      const res = await this.api(`/device/update/${this.renameDevice.id}`, {
        method: 'PUT', json: { alias: this.renameDeviceForm.alias },
      });
      if (res && res.code === 0) {
        this.renameDevice.alias = this.renameDeviceForm.alias;
        this.renameDevice = null;
        alert('已保存');
        this.loadAllDevices();
      } else { alert('保存失败：' + ((res && res.msg) || '')); }
    },
    openDeviceBind(d) {
      this.bindDevice = d;
      this.bindDeviceAgentId = '';
    },
    async saveDeviceBind() {
      if (!this.bindDeviceAgentId || !this.bindDevice) return;
      const res = await this.api(`/device/bind/${this.bindDeviceAgentId}/${encodeURIComponent(this.bindDevice.macAddress || this.bindDevice.id)}`, { method: 'POST' });
      if (res && res.code === 0) {
        this.bindDevice = null;
        alert('已绑定');
        this.loadAllDevices();
      } else { alert('绑定失败：' + ((res && res.msg) || '')); }
    },
    async unbindDevice(d) {
      if (!confirm(`确定解绑设备「${d.alias || d.macAddress}」吗？`)) return;
      const res = await this.api('/device/unbind', { method: 'POST', json: { deviceId: d.id } });
      if (res && res.code === 0) { alert('已解绑'); this.loadAllDevices(); }
      else { alert('解绑失败：' + ((res && res.msg) || '')); }
    },
    selectPage(key) {
      this.active = key;
      this.openIdx = null;
      this.debugState = {};
      this.sidebarOpen = false;
      if (key === 'devices') this.loadAllDevices();
      if (key === 'chat') {
        const agentId = this.chatAgentId || (this.agents[0] && this.agents[0].id);
        if (agentId) { this.chatAgentId = agentId; this.loadSessions(agentId, true); }
      }
      if (key === 'voices' && !this.voices.length) this.loadVoices();
      if (key === 'memory') {
        if (!this.memoryAgents.length) this.loadMemoryAgents();
        if (!this.modelOptions.Memory.length) this.loadModelOptions();
      }
      if (key === 'mcp' && this.mcpAgentId) this.loadMcpInfo();
      if (key === 'models') this.loadModelsByType();
      const lazyLoaders = {
        knowledge: () => this.loadDatasets(),
        params: () => this.loadParams(),
        users: () => this.loadUsers(),
        templates: () => this.loadTemplates(),
        ota: () => this.loadOta(),
        dicts: () => this.loadDicts(),
        correctwords: () => this.loadCorrectFiles(),
        servers: () => this.loadServers(),
      };
      if (lazyLoaders[key]) lazyLoaders[key]();
    },
    openChat(agent) {
      this.active = 'chat';
      this.chatAgentId = agent.id;
      this.loadSessions(agent.id, true);
    },
    async reloadChatSessions() {
      if (this.chatAgentId) this.loadSessions(this.chatAgentId, true);
    },
    async deleteChatSession(s) {
      if (!confirm(`确定删除会话「${s.title || s.sessionId}」吗？`)) return;
      // 后端暂无会话删除端点；该能力依赖 Java 补 DELETE /agent/{id}/chat-history/{sessionId}
      const res = await this.api(`/agent/${this.chatAgentId}/chat-history/${s.sessionId}`, { method: 'DELETE' });
      if (res && res.code === 0) {
        this.chatSessions = this.chatSessions.filter((x) => x.sessionId !== s.sessionId);
        if (this.chatSessionId === s.sessionId) { this.chatSessionId = ''; this.chatHistory = []; }
        alert('已删除');
      } else {
        alert('删除失败：' + ((res && res.msg) || '当前后端版本可能不支持会话删除'));
      }
    },
    async openAgentEdit(agent) {
      await this.loadModelOptions();
      const detail = await this.api(`/agent/${agent.id}`);
      const d = (detail && detail.data) || {};
      this.editForm = {
        id: d.id,
        agentName: d.agentName || '',
        llmModelId: d.llmModelId || (this.modelOptions.LLM[0] || {}).id,
        ttsModelId: d.ttsModelId || (this.modelOptions.TTS[0] || {}).id,
        ttsVoiceId: d.ttsVoiceId || '',
        memModelId: d.memModelId || (this.modelOptions.Memory[0] || {}).id,
        intentModelId: d.intentModelId || (this.modelOptions.Intent[0] || {}).id,
        asrModelId: d.asrModelId || (this.modelOptions.ASR[0] || {}).id,
        chatHistoryConf: d.chatHistoryConf || 2,
        ttsRate: d.ttsRate,
        systemPrompt: d.systemPrompt || '',
      };
      this.editAgent = agent;
      this.loadEditVoices();
      this.loadAgentBoundDevices(agent.id);
    },
    createAgent() {
      this.loadModelOptions().then(() => {
        this.editForm = {
          agentName: '',
          llmModelId: (this.modelOptions.LLM[0] || {}).id,
          ttsModelId: (this.modelOptions.TTS[0] || {}).id,
          ttsVoiceId: '',
          memModelId: (this.modelOptions.Memory[0] || {}).id,
          intentModelId: (this.modelOptions.Intent[0] || {}).id,
          asrModelId: (this.modelOptions.ASR[0] || {}).id,
          chatHistoryConf: 2,
          ttsRate: 0,
          systemPrompt: '',
        };
        this.editAgent = { id: '' };
        this.loadEditVoices();
      });
    },
    async loadModelOptions() {
      const types = ['LLM', 'TTS', 'Memory', 'ASR', 'VLLM', 'Intent'];
      await Promise.all(types.map(async (t) => {
        const res = await this.api(`/models/names?modelType=${t}`);
        this.modelOptions[t] = (res && res.code === 0 && res.data) || [];
      }));
    },
    async loadEditVoices() {
      if (!this.editForm.ttsModelId) { this.editVoices = []; return; }
      const res = await this.api(`/models/${this.editForm.ttsModelId}/voices`);
      this.editVoices = (res && res.code === 0 && res.data) || [];
    },
    async saveAgent() {
      const ok = await this.persistAgent();
      if (ok) {
        alert('已保存，可在下方绑定设备');
      }
    },
    /** 保存智能体（新建或更新），成功后回填 editAgent.id 并刷新列表。返回是否成功。 */
    async persistAgent() {
      if (!this.editForm.agentName) { alert('请填写名字'); return false; }
      const payload = {
        agentName: this.editForm.agentName,
        llmModelId: this.editForm.llmModelId,
        ttsModelId: this.editForm.ttsModelId,
        ttsVoiceId: this.editForm.ttsVoiceId,
        memModelId: this.editForm.memModelId,
        intentModelId: this.editForm.intentModelId,
        asrModelId: this.editForm.asrModelId,
        chatHistoryConf: this.editForm.chatHistoryConf,
        systemPrompt: this.editForm.systemPrompt,
        ttsRate: this.editForm.ttsRate,
      };
      let res;
      if (this.editAgent.id) {
        res = await this.api(`/agent/${this.editAgent.id}`, { method: 'PUT', json: payload });
      } else {
        res = await this.api('/agent', { method: 'POST', json: payload });
        if (res && res.code === 0 && res.data) {
          // 后端返回纯字符串 agentId（Result<String>）
          const newId = typeof res.data === 'string' ? res.data : (res.data.id || res.data);
          this.editAgent = { id: newId || '', agentName: this.editForm.agentName };
          this.editForm.id = this.editAgent.id;
        }
      }
      if (res && res.code === 0) {
        await this.loadAgents();
        this.loadAgentBoundDevices(this.editAgent.id);
        return true;
      }
      alert('保存失败：' + ((res && res.msg) || ''));
      return false;
    },
    async loadAgentBoundDevices(agentId) {
      if (!agentId) { this.agentBoundDevices = []; return; }
      const res = await this.api(`/device/bind/${agentId}`, { method: 'POST', json: {} });
      this.agentBoundDevices = (res && res.code === 0 && res.data) || [];
    },
    async bindDeviceByCode() {
      if (!/^\d{6}$/.test(this.agentBindCode)) { alert('请输入设备上的 6 位数字验证码'); return; }
      // 智能体未保存（新建后直接绑定）：先自动保存拿到 id 再绑定，绝不静默
      if (!this.editAgent.id) {
        const saved = await this.persistAgent();
        if (!saved) { alert('请先填写智能体名字并保存，再绑定设备'); return; }
      }
      this.agentBindBusy = true;
      try {
        const res = await this.api(`/device/bind/${this.editAgent.id}/${this.agentBindCode}`, { method: 'POST' });
        if (res && res.code === 0) {
          this.agentBindCode = '';
          alert('设备绑定成功');
          this.loadAgentBoundDevices(this.editAgent.id);
        } else { alert('绑定失败：' + ((res && res.msg) || '验证码错误或已过期')); }
      } catch (e) {
        alert('绑定请求异常：' + (e.message || '网络错误'));
      } finally { this.agentBindBusy = false; }
    },
    async manualAddDevice() {
      if (!this.manualDeviceForm.macAddress) { alert('请填写 MAC 地址'); return; }
      if (!this.editAgent.id) {
        const saved = await this.persistAgent();
        if (!saved) { alert('请先填写智能体名字并保存，再添加设备'); return; }
      }
      this.agentBindBusy = true;
      try {
        const payload = { macAddress: this.manualDeviceForm.macAddress };
        if (this.manualDeviceForm.board) payload.board = this.manualDeviceForm.board;
        if (this.manualDeviceForm.appVersion) payload.appVersion = this.manualDeviceForm.appVersion;
        const res = await this.api('/device/manual-add', { method: 'POST', json: payload });
        if (res && res.code === 0) {
          this.manualDeviceForm = { board: '', appVersion: '', macAddress: '' };
          alert('设备已添加并绑定');
          this.loadAgentBoundDevices(this.editAgent.id);
        } else { alert('添加失败：' + ((res && res.msg) || '')); }
      } finally { this.agentBindBusy = false; }
    },
    async unbindAgentDevice(d) {
      if (!confirm(`确定解绑「${d.alias || d.macAddress}」吗？`)) return;
      const res = await this.api('/device/unbind', { method: 'POST', json: { deviceId: d.id || d.device_id } });
      if (res && res.code === 0) { alert('已解绑'); this.loadAgentBoundDevices(this.editAgent.id); }
      else { alert('解绑失败：' + ((res && res.msg) || '')); }
    },
    async deleteAgent(a) {
      if (!confirm(`确定删除智能体「${a.agentName}」吗？`)) return;
      const res = await this.api(`/agent/${a.id}`, { method: 'DELETE' });
      if (res && res.code === 0) this.loadAgents();
      else alert('删除失败：' + ((res && res.msg) || ''));
    },
    async loadDatasets() {
      const res = await this.api('/datasets?page=1&page_size=50');
      this.datasets = (res && res.data && res.data.list) || [];
    },
    async createDataset() {
      if (!this.newDatasetName) return;
      const res = await this.api('/datasets', { method: 'POST', json: { name: this.newDatasetName } });
      if (res && res.code === 0) { this.newDatasetName = ''; this.loadDatasets(); }
      else alert('创建失败：' + ((res && res.msg) || ''));
    },
    async deleteDataset(d) {
      if (!confirm(`确定删除知识库「${d.name}」吗？`)) return;
      const res = await this.api(`/datasets/${d.id}`, { method: 'DELETE' });
      if (res && res.code === 0) this.loadDatasets();
      else alert('删除失败：' + ((res && res.msg) || ''));
    },
    async loadParams() {
      const res = await this.api('/admin/params/page?page=1&limit=100');
      this.sysParams = (res && res.data && res.data.list) || [];
    },
    async saveParam() {
      const res = await this.api('/admin/params', { method: 'PUT', json: this.editParam });
      if (res && res.code === 0) { this.editParam = null; this.loadParams(); }
      else alert('保存失败：' + ((res && res.msg) || ''));
    },
    async loadUsers() {
      const res = await this.api('/admin/users?page=1&limit=100');
      this.users = (res && res.data && res.data.list) || [];
    },
    async toggleUserStatus(u) {
      const newStatus = u.status === 1 ? 0 : 1;
      const res = await this.api(`/admin/users/changeStatus/${newStatus}`, { method: 'PUT', json: [u.userid] });
      if (res && res.code === 0) { u.status = newStatus; }
      else alert('操作失败：' + ((res && res.msg) || ''));
    },
    async loadTemplates() {
      const res = await this.api('/agent/template/page?page=1&limit=100');
      if (res && res.code === 401) {
        this.templates = [];
        alert('登录已过期，请刷新页面重新登录');
        return;
      }
      this.templates = (res && res.data && res.data.list) || [];
      if (!this.templates.length && res && res.code === 0) {
        console.warn('[templates] 接口正常但列表为空', res);
      }
    },
    async loadOta() {
      const res = await this.api('/otaMag?page=1&limit=100');
      this.otaList = (res && res.data && res.data.list) || [];
    },
    async loadDicts() {
      const res = await this.api('/admin/dict/type/page?page=1&limit=100');
      this.dictTypes = (res && res.data && res.data.list) || [];
    },
    async loadDictData() {
      if (!this.activeDictType) { this.dictData = []; return; }
      const res = await this.api(`/admin/dict/data/type/${this.activeDictType}`);
      this.dictData = (res && res.code === 0 && res.data) || [];
    },
    async loadCorrectFiles() {
      const res = await this.api('/correct-word/file/list?page=1&limit=100');
      this.correctFiles = (res && res.data && res.data.list) || [];
    },
    async saveCorrectFile() {
      const payload = { fileName: this.editCorrect.fileName, content: this.editCorrect.content };
      let res;
      if (this.editCorrect.id) {
        res = await this.api(`/correct-word/file/${this.editCorrect.id}`, { method: 'PUT', json: payload });
      } else {
        res = await this.api('/correct-word/file', { method: 'POST', json: payload });
      }
      if (res && res.code === 0) { this.editCorrect = null; this.loadCorrectFiles(); }
      else alert('保存失败：' + ((res && res.msg) || ''));
    },
    async deleteCorrectFile(f) {
      if (!confirm(`确定删除替换词文件「${f.fileName}」吗？`)) return;
      const res = await this.api(`/correct-word/file/${f.id}`, { method: 'DELETE' });
      if (res && res.code === 0) this.loadCorrectFiles();
      else alert('删除失败：' + ((res && res.msg) || ''));
    },
    async loadServers() {
      const res = await this.api('/admin/server/server-list');
      this.serverList = (res && res.code === 0 && res.data) || [];
    },

    // ===== 记忆编辑 =====
    openFactEdit(f) {
      this.editFact = f;
      this.editFactForm = { content: f.content, category: f.category || 'general' };
    },
    async saveFactEdit() {
      if (!this.editFactForm.content) return;
      const res = await this.api(`/memory/facts/${this.editFact.fact_id}`, {
        method: 'PUT',
        json: { agent_id: this.memoryAgentId, content: this.editFactForm.content, category: this.editFactForm.category },
      });
      if (res && res.code === 0) { this.editFact = null; this.loadMemoryFacts(); alert('已保存'); }
      else { alert('保存失败：' + ((res && res.msg) || '')); }
    },

    // ===== 字典 CRUD =====
    openDictEdit(d) {
      this.editDictData = d
        ? { ...d }
        : { dictType: this.activeDictType, dictLabel: '', dictValue: '', sort: 0, remark: '' };
    },
    async saveDictData() {
      const isEdit = !!this.editDictData.id;
      const path = isEdit ? '/admin/dict/data/update' : '/admin/dict/data/save';
      const res = await this.api(path, {
        method: 'POST', json: this.editDictData,
      });
      if (res && res.code === 0) { this.editDictData = null; this.loadDictData(); alert('已保存'); }
      else { alert('保存失败：' + ((res && res.msg) || '可能需要超级管理员权限')); }
    },
    async deleteDictData(d) {
      if (!confirm(`确定删除字典项「${d.dictLabel}」吗？`)) return;
      const res = await this.api('/admin/dict/data/delete', { method: 'POST', json: [d.id] });
      if (res && res.code === 0) { this.loadDictData(); alert('已删除'); }
      else { alert('删除失败：' + ((res && res.msg) || '')); }
    },

    // ===== OTA 上传/删除 =====
    onOtaFilePicked(e) {
      this.otaUploadFile = (e.target.files && e.target.files[0]) || null;
    },
    async uploadOta() {
      if (!this.otaUploadFile) return;
      this.otaUploading = true;
      try {
        const form = new FormData();
        form.append('file', this.otaUploadFile);
        const resp = await fetch(API_BASE + '/otaMag/upload', {
          method: 'POST', headers: this.authHeaders(), body: form,
        });
        const res = await resp.json().catch(() => null);
        if (res && res.code === 0) {
          this.otaUploadFile = null;
          if (this.$refs.otaFileInput) this.$refs.otaFileInput.value = '';
          this.loadOta();
          alert('固件已上传');
        } else {
          alert('上传失败：' + ((res && res.msg) || '仅支持 .bin/.apk，且需超级管理员权限'));
        }
      } finally {
        this.otaUploading = false;
      }
    },
    async deleteOta(o) {
      if (!confirm(`确定删除固件「${o.firmwareVersion || o.id}」吗？`)) return;
      const res = await this.api(`/otaMag/${o.id}`, { method: 'DELETE' });
      if (res && res.code === 0) { this.loadOta(); alert('已删除'); }
      else { alert('删除失败：' + ((res && res.msg) || '')); }
    },
    downloadOta(o) {
      window.open(API_BASE + '/otaMag/download/' + (o.uuid || o.id), '_blank');
    },

    // ===== 模板一键创建 =====
    async createAgentFromTemplate(t) {
      if (!confirm(`用模板「${t.agentName}」创建新智能体？`)) return;
      const payload = {
        agentName: (t.agentName || '模板智能体') + '-副本',
        templateId: t.id,
      };
      const res = await this.api('/agent', { method: 'POST', json: payload });
      if (res && res.code === 0) {
        alert('已创建，可在「智能体」页编辑');
        this.loadAgents();
      } else { alert('创建失败：' + ((res && res.msg) || '')); }
    },

    // ===== 模型 CRUD（供应器动态表单 + 自定义 OpenAI 兼容接口） =====
    async loadModelProviders() {
      const res = await this.api(`/models/${this.activeModelType}/provideTypes`);
      this.modelProviders = (res && res.code === 0 && res.data) || [];
    },
    parseProviderFields(providerCode) {
      if (providerCode === '__custom_openai__') {
        return [
          { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'sk-...' },
          { key: 'base_url', label: '接口地址 Base URL', placeholder: 'https://api.example.com/v1' },
          { key: 'model_name', label: '模型名 Model', placeholder: 'gpt-4o / glm-4-flash / ...' },
        ];
      }
      const p = this.modelProviders.find((x) => x.providerCode === providerCode);
      if (!p || !p.fields) return [];
      try {
        const arr = typeof p.fields === 'string' ? JSON.parse(p.fields) : p.fields;
        return (arr || []).map((f) => ({
          key: f.key || f.field || f.name,
          label: f.label || f.title || f.key || f.name,
          type: (f.type === 'password' || /key|secret|token/i.test(String(f.key || f.name))) ? 'password' : 'text',
          placeholder: f.placeholder || f.description || '',
        })).filter((f) => f.key);
      } catch (e) { return []; }
    },
    onProviderChange() {
      this.providerFields = this.parseProviderFields(this.editModelCfg.providerCode);
      if (this.editModelCfg.providerCode === '__custom_openai__') {
        this.editModelCfg.customType = this.editModelCfg.customType || 'openai';
        this.editModelCfg.config = { api_key: '', base_url: '', model_name: '' };
      } else {
        this.editModelCfg.config = {};
      }
    },
    addCustomField() {
      const k = (this.newCustomFieldKey || '').trim();
      if (!k) return;
      if (this.providerFields.some((f) => f.key === k)) { alert('字段已存在'); return; }
      this.providerFields = [...this.providerFields, { key: k, label: k, type: 'text', placeholder: k }];
      this.editModelCfg.config = { ...this.editModelCfg.config, [k]: '' };
      this.newCustomFieldKey = '';
    },
    removeCustomField(k) {
      this.providerFields = this.providerFields.filter((f) => f.key !== k);
      const cfg = { ...this.editModelCfg.config };
      delete cfg[k];
      this.editModelCfg.config = cfg;
    },
    async openModelEdit(m) {
      if (!this.modelProviders.length) await this.loadModelProviders();
      if (m) {
        // 编辑：拉详情拿 configJson + providerCode
        const res = await this.api(`/models/${m.id}`);
        const d = (res && res.data) || {};
        const cfg = d.configJson || {};
        this.editModelCfg = {
          id: m.id,
          providerCode: d.providerCode || (cfg.type ? '__custom_openai__' : (this.modelProviders[0] || {}).providerCode),
          modelName: d.modelName || m.modelName,
          customType: cfg.type || 'openai',
          config: { ...cfg },
        };
      } else {
        this.editModelCfg = {
          id: '',
          providerCode: (this.modelProviders[0] || {}).providerCode || '__custom_openai__',
          modelName: '',
          customType: 'openai',
          config: {},
        };
      }
      this.providerFields = this.parseProviderFields(this.editModelCfg.providerCode);
      // 自定义接口编辑：把 configJson 现有键都展示为可编辑字段
      if (this.editModelCfg.providerCode === '__custom_openai__' && this.editModelCfg.id) {
        const extra = Object.keys(this.editModelCfg.config).filter((k) => !this.providerFields.some((f) => f.key === k));
        this.providerFields = [...this.providerFields, ...extra.map((k) => ({ key: k, label: k, type: 'text', placeholder: k }))];
      }
    },
    async saveModelConfig() {
      if (!this.editModelCfg.modelName) return;
      this.modelSaving = true;
      try {
        const isCustom = this.editModelCfg.providerCode === '__custom_openai__';
        const providerCode = isCustom ? 'custom' : this.editModelCfg.providerCode;
        const config = { ...this.editModelCfg.config };
        // Python 端按 configJson.type 路由到 core/providers/{type}.py —— 必须始终注入，
        // 否则试听/链路模拟器报「请求体缺少 type 字段」（常规供应器 type=providerCode，如 doubao_v3）
        config.type = isCustom ? (this.editModelCfg.customType || 'openai') : providerCode;
        const body = {
          modelName: this.editModelCfg.modelName,
          isDefault: 0,
          isEnabled: 1,
          configJson: config,
        };
        let res;
        if (this.editModelCfg.id) {
          res = await this.api(`/models/${this.activeModelType}/${providerCode}/${this.editModelCfg.id}`, { method: 'PUT', json: body });
        } else {
          res = await this.api(`/models/${this.activeModelType}/${providerCode}`, { method: 'POST', json: body });
        }
        if (res && res.code === 0) {
          this.editModelCfg = null;
          this.loadModelsByType();
          alert('已保存');
        } else {
          alert('保存失败：' + ((res && res.msg) || '可能需要超级管理员权限'));
        }
      } finally {
        this.modelSaving = false;
      }
    },
    async deleteModelConfig(m) {
      if (!confirm(`确定删除模型「${m.modelName}」吗？`)) return;
      const res = await this.api(`/models/${m.id}`, { method: 'DELETE' });
      if (res && res.code === 0) { this.loadModelsByType(); alert('已删除'); }
      else { alert('删除失败：' + ((res && res.msg) || '')); }
    },

    // ===== 模型管理（9 类型 tab + 一键测试） =====
    async loadModelsByType() {
      const types = this.MODEL_TYPES.map((t) => t.value);
      await Promise.all(types.map(async (t) => {
        const res = await this.api(`/models/list?modelType=${t}&page=1&limit=100`);
        const list = (res && res.data && res.data.list) || [];
        this.modelsByType = { ...this.modelsByType, [t]: list };
        if (t === 'TTS') {
          this.ttsModels = list;
          this.stats[3].value = list.length;
          const def = list.find((m) => m.isDefault);
          this.defaultTtsName = def ? def.modelName : '未设置';
        }
      }));
    },
    switchModelType(t) {
      this.activeModelType = t;
      if (!this.modelsByType[t]) this.loadModelsByType();
    },
    modelTypeCount(t) {
      return (this.modelsByType[t] || []).length;
    },
    async testModel(m) {
      this.testState = { ...this.testState, [m.id]: { loading: true, ok: null, text: '⏳ 测试中…' } };
      try {
        const res = await this.api(`/models/modelTest?modelId=${encodeURIComponent(m.id)}&modelType=${this.activeModelType}`);
        if (res && res.code === 0 && res.data) {
          const d = res.data;
          this.testState = { ...this.testState, [m.id]: {
            loading: false, ok: !!d.ok,
            text: (d.ok ? '✅ ' : '❌ ') + (d.message || '') + (d.elapsed_ms != null ? `（${d.elapsed_ms}ms）` : ''),
          } };
        } else {
          this.testState = { ...this.testState, [m.id]: { loading: false, ok: false, text: '❌ ' + ((res && res.msg) || '测试失败') } };
        }
      } catch (e) {
        this.testState = { ...this.testState, [m.id]: { loading: false, ok: false, text: '❌ 请求异常：' + (e.message || '') } };
      }
    },
    async testMcp() {
      if (!this.mcpAgentId) return;
      this.mcpTesting = true;
      this.mcpTestResult = null;
      try {
        const res = await this.api(`/agent/mcp/test/${this.mcpAgentId}`);
        if (res && res.code === 0 && res.data) {
          this.mcpTestResult = res.data;
        } else {
          this.mcpTestResult = { ok: false, message: (res && res.msg) || '测试失败', elapsed_ms: 0 };
        }
      } catch (e) {
        this.mcpTestResult = { ok: false, message: '请求异常：' + (e.message || ''), elapsed_ms: 0 };
      } finally {
        this.mcpTesting = false;
      }
    },

    // ===== MCP 接入点 =====
    async loadMcpInfo() {
      this.mcpAddress = '';
      this.mcpTools = [];
      if (!this.mcpAgentId) return;
      const [addrRes, toolsRes] = await Promise.all([
        this.api(`/agent/mcp/address/${this.mcpAgentId}`),
        this.api(`/agent/mcp/tools/${this.mcpAgentId}`),
      ]);
      if (addrRes && addrRes.code === 0) this.mcpAddress = (addrRes.data || '').toString();
      else if (addrRes && addrRes.msg) this.mcpAddress = '';
      if (toolsRes && toolsRes.code === 0) {
        const data = toolsRes.data;
        this.mcpTools = Array.isArray(data) ? data : (data && data.tools) || [];
      }
    },
    copyMcpAddress() {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(this.mcpAddress).then(() => alert('已复制'));
      } else {
        const el = document.createElement('textarea');
        el.value = this.mcpAddress;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);
        alert('已复制');
      }
    },

    // ===== 链路模拟器 =====
    simStageClass(stage) {
      return {
        'sim-stage--done': this.simStage[stage] === 'done',
        'sim-stage--loading': this.simStage[stage] === 'loading',
        'sim-stage--error': this.simStage[stage] === 'error',
      };
    },
    simLog(line) {
      this.simLogs.push(`[${new Date().toLocaleTimeString()}] ${line}`);
    },
    async toggleSimListen() {
      if (this.simListening) {
        this.stopSimRecorder();
        return;
      }
      // 真实 ASR：MediaRecorder 录音 → 服务端识别（与设备同一 ASR 引擎）
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
        alert('当前浏览器不支持录音（需要 HTTPS 页面 + MediaRecorder）');
        return;
      }
      const agent = this.agents.find((a) => a.id === this.simAgentId) || null;
      let asrModelId = this.simAsrModelId;
      if (!asrModelId) {
        // 拉详情取 asrModelId（/agent/list 不带该字段）
        try {
          const d = await this.api(`/agent/${this.simAgentId}`);
          if (d && d.code === 0 && d.data) {
            asrModelId = d.data.asrModelId || '';
            this.simAsrModelId = asrModelId;
          }
        } catch (e) { /* 详情失败时下面统一提示 */ }
      }
      if (!asrModelId) {
        alert('该智能体未配置 ASR 模型，请先在「智能体」页编辑选择语音识别引擎');
        return;
      }
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        alert('无法访问麦克风：' + (e.message || e.name || '请检查浏览器权限（页面需 https）'));
        return;
      }
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks = [];
      recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        if (!blob.size) {
          this.simStage.asr = 'error';
          this.simError.asr = '未录到音频';
          this.simLog('ASR 失败: 未录到音频');
          return;
        }
        this.simStage.asr = 'loading';
        this.simError.asr = '';
        this.simLog(`上传音频 ${(blob.size / 1024).toFixed(1)}KB → 服务端 ASR 识别中…`);
        try {
          const res = await this.api(`/models/asrRecognize?modelId=${encodeURIComponent(this.simAsrModelId)}`, {
            method: 'POST', contentType: blob.type || 'audio/webm', rawBody: blob,
          });
          if (res && res.code === 0 && res.data) {
            const text = (res.data.text || '').trim();
            if (!text) {
              this.simStage.asr = 'error';
              this.simError.asr = '识别结果为空（请靠近麦克风再说一次）';
              this.simLog('ASR 失败: 识别结果为空');
            } else {
              this.simInputText = text;
              this.simAsrText = text;
              this.simStage.asr = 'done';
              this.simLog(`ASR（服务端 ${res.data.elapsed_ms}ms）: ${text}`);
            }
          } else {
            throw new Error((res && res.msg) || ('错误码 ' + (res && res.code)));
          }
        } catch (e) {
          this.simStage.asr = 'error';
          this.simError.asr = '识别失败：' + (e.message || '网络异常');
          this.simLog(`ASR 失败: ${e.message || '网络异常'}`);
        }
      };
      recorder.start();
      this.simRecorder = recorder;
      this.simListening = true;
      this.simStage.asr = 'loading';
      this.simError.asr = '';
      this.simLog('录音中…（真实上传服务端 ASR，再点一次结束）');
    },
    stopSimRecorder() {
      if (this.simRecorder && this.simRecorder.state !== 'inactive') {
        try { this.simRecorder.stop(); } catch (e) { /* noop */ }
      }
      this.simRecorder = null;
      this.simListening = false;
    },
    async runSimPipeline() {
      const text = this.simInputText;
      if (!text || !this.simAgentId || this.simBusy) return;
      this.simBusy = true;
      this.simLogs = [];
      this.simStage = { asr: '', llm: '', tts: '' };
      this.simError = { asr: '', llm: '', tts: '' };
      this.simLlmReply = '';
      if (this.simAudioUrl) { URL.revokeObjectURL(this.simAudioUrl); this.simAudioUrl = ''; }
      // /agent/list 不返回 llmModelId 等字段（只有显示名），必须拉详情拿真实模型 ID
      const detailRes = await this.api(`/agent/${this.simAgentId}`);
      const agent = (detailRes && detailRes.code === 0 && detailRes.data) || null;
      if (!agent || !agent.llmModelId) {
        this.simStage.llm = 'error';
        this.simError.llm = '该智能体未配置 LLM 模型，请先在「智能体」页编辑选择大脑';
        this.simLog('LLM 失败: 智能体缺少 llmModelId');
        this.simBusy = false;
        return;
      }
      try {
        // ① ASR（文本直接作为识别结果）
        this.simStage.asr = 'loading';
        await new Promise((r) => setTimeout(r, 60));
        this.simAsrText = text;
        this.simStage.asr = 'done';
        this.simLog(`ASR: ${text}`);

        // ② LLM
        this.simStage.llm = 'loading';
        const t0 = performance.now();
        const llmRes = await this.api(`/models/llmPreview?modelId=${encodeURIComponent(agent.llmModelId)}&text=${encodeURIComponent(text)}&systemPrompt=${encodeURIComponent(agent.systemPrompt || '')}`);
        if (llmRes && llmRes.code === 0 && llmRes.data) {
          this.simLlmReply = llmRes.data.reply || '';
          this.simStage.llm = 'done';
          this.simLog(`LLM (${Math.round(performance.now() - t0)}ms + ${llmRes.data.elapsed_ms || 0}ms服务端): ${this.simLlmReply.slice(0, 80)}`);
        } else {
          this.simStage.llm = 'error';
          this.simError.llm = (llmRes && llmRes.msg) || 'LLM 调用失败';
          this.simLog(`LLM 失败: ${this.simError.llm}`);
          this.simBusy = false;
          return;
        }

        // ③ TTS（60 字截断；音色需把表 id 转成 tts_voice code）
        this.simStage.tts = 'loading';
        const ttsText = this.simLlmReply.slice(0, 60);
        if (ttsText !== this.simLlmReply) this.simLog(`TTS 文本超 60 字，已截断`);
        let voiceCode = agent.ttsVoiceId || '';
        if (agent.ttsModelId && agent.ttsVoiceId) {
          const voicesRes = await this.api(`/models/${encodeURIComponent(agent.ttsModelId)}/voices`);
          const vlist = (voicesRes && voicesRes.code === 0 && voicesRes.data) || [];
          const hit = vlist.find((v) => v.id === agent.ttsVoiceId);
          if (hit && hit.ttsVoice) {
            voiceCode = hit.ttsVoice;
          } else if (!hit) {
            this.simLog(`音色表未找到 ${agent.ttsVoiceId}，原样传给合成端`);
          }
        }
        const t1 = performance.now();
        const blob = await this.api(`/models/ttsPreview?modelId=${encodeURIComponent(agent.ttsModelId)}&voice=${encodeURIComponent(voiceCode)}&text=${encodeURIComponent(ttsText)}`);
        if (!blob || blob.size < 200) {
          throw new Error('TTS 返回空音频（音色或模型配置可能有误）');
        }
        this.simAudioUrl = URL.createObjectURL(blob);
        this.simStage.tts = 'done';
        this.simLog(`TTS (${Math.round(performance.now() - t1)}ms): 音频 ${(blob.size / 1024).toFixed(1)}KB · 音色 ${voiceCode}`);
        this.$nextTick(() => {
          if (this.$refs.simAudioEl) this.$refs.simAudioEl.play().catch(() => {});
        });
      } catch (e) {
        const stage = this.simStage.llm !== 'done' ? 'llm' : 'tts';
        this.simStage[stage] = 'error';
        this.simError[stage] = (e && e.message) || '请求异常';
        this.simLog(`${stage.toUpperCase()} 异常: ${this.simError[stage]}`);
      } finally {
        this.simBusy = false;
      }
    },

    // ===== 记忆视图（时间轴/图谱，移植原控制台） =====
    switchMemView(mode) {
      this.memViewMode = mode;
      if (mode === 'graph') {
        this.$nextTick(() => this.drawMemGraph());
      }
    },
    memTimeOf(ts) {
      return String(ts || '').slice(11, 19) || '';
    },
    memTrustStyle(v) {
      const n = Number(v);
      let color = '#a08e96';
      if (n >= 0.75) color = '#FF8FAB';
      else if (n >= 0.4) color = '#d98a2b';
      return { color, borderColor: color };
    },
    drawMemGraph() {
      const canvas = this.$refs.memGraphCanvas;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      const facts = this.memoryFacts || [];
      if (!facts.length) return;

      // 实体聚合（fact.entities 数组，详情接口提供；无则归入"未关联"）
      const entityMap = new Map();
      facts.forEach((f) => {
        const ents = Array.isArray(f.entities) && f.entities.length ? f.entities : [];
        if (!ents.length) {
          const key = '__orphan__';
          if (!entityMap.has(key)) entityMap.set(key, { count: 0, facts: [], name: '未关联' });
          entityMap.get(key).count += 1;
          entityMap.get(key).facts.push(f);
        }
        ents.forEach((e) => {
          const name = typeof e === 'string' ? e : (e.name || String(e));
          if (!entityMap.has(name)) entityMap.set(name, { count: 0, facts: [], name });
          entityMap.get(name).count += 1;
          entityMap.get(name).facts.push(f);
        });
      });

      const PALETTE = ['#FF8FAB', '#FFB6C6', '#FFD86B', '#9EE6D0', '#B8A9F5', '#8FC7FF', '#FFC3A0', '#A8E6CF'];
      // 实体节点环形布局
      const entities = Array.from(entityMap.values());
      const cx = W / 2, cy = H / 2;
      const R = Math.min(W, H) * 0.34;
      const nodes = entities.map((e, i) => {
        const angle = (2 * Math.PI * i) / Math.max(entities.length, 1) - Math.PI / 2;
        return {
          ...e,
          x: cx + R * Math.cos(angle),
          y: cy + R * Math.sin(angle),
          r: Math.min(16 + e.count * 5, 34),
          color: e.count >= 3 ? '#FF8FAB' : PALETTE[i % PALETTE.length],
          hot: e.count >= 3,
        };
      });

      // 连线（实体→其记忆的缩略点：布在实体外侧小圆）
      ctx.lineWidth = 1.2;
      nodes.forEach((n) => {
        n.facts.forEach((f, fi) => {
          const fa = Math.atan2(n.y - cy, n.x - cx);
          const fr = R + 60 + (fi % 4) * 26;
          const fx = cx + fr * Math.cos(fa);
          const fy = cy + fr * Math.sin(fa);
          ctx.strokeStyle = 'rgba(180,150,170,0.35)';
          ctx.beginPath();
          ctx.moveTo(n.x, n.y);
          ctx.lineTo(fx, fy);
          ctx.stroke();
          // 记忆小点
          ctx.fillStyle = 'rgba(184,169,245,0.75)';
          ctx.beginPath();
          ctx.arc(fx, fy, 3.4, 0, 2 * Math.PI);
          ctx.fill();
        });
      });

      // 实体节点 + 标签
      nodes.forEach((n) => {
        if (n.hot) {
          ctx.shadowBlur = 14; ctx.shadowColor = 'rgba(255,143,171,0.5)';
        } else {
          ctx.shadowBlur = 5; ctx.shadowColor = 'rgba(255,143,171,0.25)';
        }
        ctx.fillStyle = n.color;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        // 标签
        ctx.fillStyle = '#4b3b44';
        ctx.font = '600 12px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(n.name.length > 10 ? n.name.slice(0, 10) + '…' : n.name, n.x, n.y + n.r + 14);
        ctx.fillStyle = '#a08e96';
        ctx.font = '10px system-ui, sans-serif';
        ctx.fillText(String(n.count), n.x, n.y + 4);
      });
    },

    catZh(c) {
      const map = { preference: '偏好', profile: '画像', habit: '习惯', event: '事件', general: '通用' };
      return map[c] || c;
    },
    // ===== 记忆引擎配置（mem_hybrid） =====
    onMemoryEngineChange() {
      this.memoryEngineApplied = '';
    },
    async applyMemoryEngine() {
      if (!this.memoryEngineAgentId || !this.memoryEngine) return;
      this.memoryEngineSaving = true;
      this.memoryEngineApplied = '';
      try {
        // 拉智能体详情 → 改 memModelId（及模型 config 的总结 LLM）→ PUT 保存
        const detail = await this.api(`/agent/${this.memoryEngineAgentId}`);
        const d = (detail && detail.code === 0 && detail.data) || null;
        if (!d) { alert('拉取智能体详情失败'); return; }

        // 若引擎支持总结 LLM（mem_hybrid / mem_local_short），更新模型 config 的 llm 字段
        if (this.memoryEngine === 'Memory_mem_hybrid' || this.memoryEngine === 'Memory_mem_local_short') {
          const cfgRes = await this.api(`/models/${this.memoryEngine}`);
          const cfg = (cfgRes && cfgRes.code === 0 && cfgRes.data) || null;
          let rawConfig = cfg && (cfg.configJson || cfg.rawConfigJson) || null;
          if (rawConfig && typeof rawConfig === 'object') {
            rawConfig = { ...rawConfig, llm: this.memorySummaryLlm || rawConfig.llm };
            const body = {
              modelName: (cfg && cfg.modelName) || this.memoryEngine,
              isDefault: (cfg && cfg.isDefault) || 0,
              isEnabled: (cfg && cfg.isEnabled) != null ? cfg.isEnabled : 1,
              configJson: rawConfig,
            };
            const providerCode = (rawConfig.type) || 'custom';
            const upd = await this.api(`/models/Memory/${providerCode}/${this.memoryEngine}`, { method: 'PUT', json: body });
            if (!(upd && upd.code === 0)) {
              // 更新模型配置失败不阻断（引擎切换仍继续），提示即可
              console.warn('[memory-engine] 更新总结 LLM 失败', upd && upd.msg);
            }
          }
        }

        const payload = {
          agentName: d.agentName,
          llmModelId: d.llmModelId,
          ttsModelId: d.ttsModelId,
          ttsVoiceId: d.ttsVoiceId,
          memModelId: this.memoryEngine,
          intentModelId: d.intentModelId,
          asrModelId: d.asrModelId,
          chatHistoryConf: d.chatHistoryConf != null ? d.chatHistoryConf : 2,
          systemPrompt: d.systemPrompt || '',
          ttsRate: d.ttsRate || 0,
        };
        const res = await this.api(`/agent/${this.memoryEngineAgentId}`, { method: 'PUT', json: payload });
        if (res && res.code === 0) {
          this.memoryEngineApplied = `✅ 已应用到「${d.agentName}」：${this.memoryEngine === 'Memory_mem_hybrid' ? '混合记忆' : '引擎'} ${this.memoryEngine}${this.memorySummaryLlm ? ' · 总结LLM ' + this.memorySummaryLlm : ''}（设备重连后生效）`;
        } else {
          alert('应用失败：' + ((res && res.msg) || ''));
        }
      } catch (e) {
        alert('应用异常：' + (e.message || ''));
      } finally {
        this.memoryEngineSaving = false;
      }
    },
    async loadMemoryAgents() {
      const res = await this.api('/memory/agents');
      this.memoryAgents = (res && res.code === 0 && res.data) || [];
      if (!this.memoryAgentId && this.memoryAgents.length) {
        this.memoryAgentId = this.memoryAgents[0].agent_id;
      }
      if (this.memoryAgentId) this.loadMemoryFacts();
    },
    selectMemAgent(id) {
      this.memoryAgentId = id;
      this.loadMemoryFacts();
    },
    async loadMemoryFacts() {
      if (!this.memoryAgentId) return;
      let qs = `?agent_id=${this.memoryAgentId}&page=1&size=50`;
      if (this.memFilterCategory) qs += `&category=${this.memFilterCategory}`;
      if (this.memFilterStatus) qs += `&status=${this.memFilterStatus}`;
      const res = await this.api(`/memory/facts${qs}`);
      this.memoryFacts = (res && res.data && res.data.list) || [];
    },
    async factFeedback(f, helpful) {
      const res = await this.api(`/memory/facts/${f.fact_id}/feedback`, { method: 'POST', json: { agent_id: this.memoryAgentId, helpful } });
      if (res && res.code === 0) {
        f.trust_score = (res.data && res.data.trust_score) || f.trust_score;
      } else { alert('操作失败：' + ((res && res.msg) || '')); }
    },
    async factReview(f, action) {
      const res = await this.api(`/memory/facts/${f.fact_id}/review`, { method: 'POST', json: { agent_id: this.memoryAgentId, action } });
      if (res && res.code === 0) { f.status = action === 'approve' ? 'active' : 'rejected'; }
      else { alert('操作失败：' + ((res && res.msg) || '')); }
    },
    async factDelete(f) {
      if (!confirm('确定删除这条记忆吗？不可恢复')) return;
      const res = await this.api(`/memory/facts/${f.fact_id}?agent_id=${this.memoryAgentId}`, { method: 'DELETE' });
      if (res && res.code === 0) { this.memoryFacts = this.memoryFacts.filter((x) => x.fact_id !== f.fact_id); }
      else { alert('删除失败：' + ((res && res.msg) || '')); }
    },
    async factCreate() {
      if (!this.memNewFact || !this.memoryAgentId) return;
      const res = await this.api('/memory/facts', { method: 'POST', json: { agent_id: this.memoryAgentId, content: this.memNewFact } });
      if (res && res.code === 0) { this.memNewFact = ''; this.loadMemoryFacts(); }
      else { alert('添加失败：' + ((res && res.msg) || '')); }
    },
    selectApiModule(key) {
      this.activeApiModule = key;
      this.openIdx = null;
      this.debugState = {};
    },
    toggleApi(idx) {
      this.openIdx = this.openIdx === idx ? null : idx;
      if (this.openIdx === idx && !this.debugState[idx]) {
        this.debugState[idx] = { query: '', body: '', result: '', loading: false };
      }
    },
    async sendRequest(api, idx) {
      const state = this.debugState[idx];
      state.loading = true;
      state.result = '';
      try {
        let url = api.p;
        const queryObj = this.safeParse(state.query) || {};
        const consumed = {};
        url = url.replace(/\$\{(\w+)\}/g, (full, key) => {
          if (queryObj[key] !== undefined) { consumed[key] = true; return encodeURIComponent(queryObj[key]); }
          return key === 'id' ? '0' : key;
        });
        const remaining = {};
        Object.keys(queryObj).forEach((k) => { if (!consumed[k]) remaining[k] = queryObj[k]; });
        const qs = new URLSearchParams(remaining).toString();
        if (qs) url += (url.includes('?') ? '&' : '?') + qs;
        const headers = this.authHeaders();
        const opts = { method: api.h, headers };
        if (api.h !== 'GET' && api.h !== 'DELETE') {
          const bodyObj = this.safeParse(state.body);
          if (bodyObj !== null) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(bodyObj); }
        }
        const t0 = performance.now();
        const resp = await fetch(API_BASE + url, opts);
        const ms = Math.round(performance.now() - t0);
        const ctype = resp.headers.get('Content-Type') || '';
        let text = await resp.text();
        try { text = JSON.stringify(JSON.parse(text), null, 2); } catch (e) {}
        state.result = `HTTP ${resp.status} · ${ms}ms\n\n${text}`;
      } catch (e) {
        state.result = '请求失败：' + e.message;
      } finally {
        state.loading = false;
      }
    },
    safeParse(t) {
      if (!t || !t.trim()) return null;
      try { return JSON.parse(t); } catch (e) { return null; }
    },
    async fetchPubConfig() {
      try {
        const resp = await fetch(`${API_BASE}/user/pub-config`);
        const data = await resp.json();
        if (data.code === 0 && data.data && data.data.sm2PublicKey) {
          this.pubKey = data.data.sm2PublicKey;
          localStorage.setItem('cc_pubkey', this.pubKey);
        }
      } catch (e) {}
    },
    refreshCaptcha() {
      this.captchaUuid = this.uuidv4();
      this.captchaSrc = `${API_BASE}/user/captcha?uuid=${this.captchaUuid}`;
    },
    uuidv4() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
    },
    async doLogin() {
      if (!this.loginForm.username || !this.loginForm.password) {
        this.loginError = '请输入用户名和密码';
        return;
      }
      this.loginLoading = true;
      this.loginError = '';
      try {
        if (!this.pubKey) await this.fetchPubConfig();
        if (!this.pubKey) throw new Error('无法获取加密公钥');
        const captchaAndPassword = this.loginForm.captcha + this.loginForm.password;
        const encryptedPassword = '04' + sm2.doEncrypt(captchaAndPassword, this.pubKey, 1);
        const resp = await fetch(`${API_BASE}/user/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: this.loginForm.username, password: encryptedPassword, captchaId: this.captchaUuid }),
        }).then((r) => r.json());
        if (resp.code === 0 && resp.data && resp.data.token) {
          const raw = JSON.stringify(resp.data);
          localStorage.setItem('cc_token', raw);
          this.token = raw;
          this.loadAll();
        } else {
          this.loginError = resp.msg || '登录失败，请检查账号密码';
          this.refreshCaptcha();
        }
      } catch (e) {
        this.loginError = '网络异常，请稍后再试';
        this.refreshCaptcha();
      } finally {
        this.loginLoading = false;
      }
    },
    doLogout() {
      localStorage.removeItem('cc_token');
      this.token = '';
      this.active = 'overview';
    },
    setTheme(id) {
      this.currentTheme = id;
      document.documentElement.setAttribute('data-theme', id);
      localStorage.setItem('cc_theme', id);
    },
  },
};
</script>

<style scoped>
.boot-progress { position: fixed; top: 0; left: 0; right: 0; z-index: 10000; padding: 6px 12px; }
.login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 32px 16px; }
.login-card { width: 100%; max-width: 400px; text-align: center; }
.login-logo { width: 72px; height: 72px; margin-bottom: 8px; }
.login-title { font-size: 1.45rem; font-weight: 600; margin: 0 0 4px; }
.login-sub { font-size: 0.85rem; color: var(--text-soft); margin: 0 0 20px; }
.field { text-align: left; margin-bottom: 14px; }
.field label { display: block; font-size: 0.8rem; color: var(--text-soft); margin-bottom: 6px; }
.captcha-row .cc-input { display: inline-block; width: calc(100% - 96px); }
.captcha-img { width: 84px; height: 38px; margin-left: 8px; border-radius: 12px; cursor: pointer; vertical-align: middle; border: 2px solid var(--primary-soft); }
.login-btn { width: 100%; margin-top: 6px; font-size: 0.95rem; }
.login-error { color: #e05d70; font-size: 0.8rem; margin: 10px 0 0; }

.shell { display: flex; gap: 24px; align-items: stretch; padding: 24px; max-width: 1280px; margin: 0 auto; height: 100vh; box-sizing: border-box; }
html, body { height: 100vh; overflow: hidden; margin: 0; }
.sidebar { width: 240px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; }
.sidebar .module-list { flex: 1; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; }
.sidebar .logout { flex-shrink: 0; }
.main { flex: 1; min-width: 0; overflow-y: auto; overscroll-behavior: contain; padding-right: 6px; }
.page { padding-bottom: 28px; }
/* 细滚动条（容器内滚动） */
.sidebar .module-list::-webkit-scrollbar, .main::-webkit-scrollbar, .modal-card::-webkit-scrollbar { width: 8px; }
.sidebar .module-list::-webkit-scrollbar-thumb, .main::-webkit-scrollbar-thumb, .modal-card::-webkit-scrollbar-thumb { background: rgba(255,143,171,.35); border-radius: 8px; }
.sidebar .module-list::-webkit-scrollbar-track, .main::-webkit-scrollbar-track, .modal-card::-webkit-scrollbar-track { background: transparent; }
.sidebar-head { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.logo { width: 40px; height: 40px; }
.sidebar-title { font-weight: 600; font-size: 1rem; }
.module-list { display: flex; flex-direction: column; gap: 10px; }
.module-item { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border: none; border-radius: var(--radius-md); background: transparent; cursor: pointer; font-size: 0.9rem; font-weight: 500; color: var(--text); transition: all 0.2s var(--ease-jelly); text-align: left; font-family: inherit; }
.module-item:hover { background: var(--primary-bg); transform: scale(1.03); }
.module-item.is-active { background: #ffe3ec; box-shadow: 0 2px 10px rgba(255, 143, 171, 0.25); }
.module-icon { width: 26px; height: 26px; flex-shrink: 0; border-radius: 9px; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; background: var(--primary-bg); }
.module-icon--voice { background: #ffeef6; }
.module-icon--knowledge { background: #eefbfd; }
.module-icon--model { background: #fdf1ff; }
.module-icon--system { background: #f3efff; }
.module-icon--contact { background: #fff8e6; }
.module-name { flex: 1; }
.logout { margin-top: 16px; width: 100%; font-size: 0.85rem; }

/* main 布局已在前文 .shell 应用窗口模式中定义（flex + 内部滚动） */
.page-title { font-size: 1.35rem; font-weight: 600; margin: 0; }
.page-sub { font-size: 0.85rem; color: var(--text-soft); margin: 4px 0 20px; }
.page-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.page-head .page-title, .page-head .page-sub { margin-bottom: 0; }
.section-title { font-size: 1rem; font-weight: 600; margin: 24px 0 12px; }
.empty-hint { color: var(--text-soft); font-size: 0.85rem; padding: 24px 0; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }
.stat-card { background: var(--surface); border-radius: var(--radius-lg); box-shadow: var(--shadow-card); padding: 20px; text-align: center; }
.stat-num { font-size: 1.8rem; font-weight: 600; color: var(--primary-strong); }
.stat-label { font-size: 0.8rem; color: var(--text-soft); margin-top: 4px; }

.agent-grid, .device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.agent-card, .device-card { background: var(--surface); border-radius: var(--radius-lg); box-shadow: var(--shadow-card); padding: 20px; }
.agent-name, .device-name { font-weight: 600; font-size: 1rem; margin-bottom: 8px; }
.agent-meta, .device-meta { font-size: 0.8rem; color: var(--text-soft); margin-bottom: 4px; }
.agent-actions { display: flex; gap: 8px; margin-top: 12px; }
.agent-actions .kawaii-pill { padding: 6px 14px; font-size: 0.8rem; }
.create-btn { margin-top: 20px; }

.voice-list { display: flex; flex-direction: column; gap: 10px; }
.voice-item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 16px; background: var(--surface); }
.voice-actions { display: flex; gap: 6px; margin-left: auto; align-items: center; }
.play-btn.danger:hover { color: #e5484d; border-color: #e5484d; }
.voice-name { flex: 1; font-weight: 500; }
.voice-lang { font-size: 0.75rem; color: var(--text-soft); }
.play-btn { padding: 6px 14px; font-size: 0.8rem; }
.select { width: auto; min-width: 220px; }

.sess-list { display: flex; flex-direction: column; gap: 10px; }
.sess-item { padding: 14px 16px; border-radius: 16px; background: var(--surface); cursor: pointer; }
.sess-item.is-active { background: var(--primary-bg); }
.sess-title { font-weight: 500; font-size: 0.9rem; }
.sess-meta { font-size: 0.75rem; color: var(--text-soft); margin-top: 4px; }

.chat-thread { margin-top: 16px; display: flex; flex-direction: column; gap: 10px; max-height: 460px; overflow-y: auto; }
.chat-bubble { max-width: 78%; padding: 12px 16px; border-radius: 18px; font-size: 0.88rem; }
.chat-user { align-self: flex-end; background: var(--primary-strong); color: #fff; border-bottom-right-radius: 6px; }
.chat-ai { align-self: flex-start; background: var(--primary-bg); color: var(--text); border-bottom-left-radius: 6px; }
.chat-play { margin-top: 6px; background: rgba(255,255,255,0.35); border: none; border-radius: var(--radius-full); padding: 4px 12px; font-size: 0.75rem; cursor: pointer; font-family: inherit; }

.model-list { display: flex; flex-direction: column; gap: 10px; }
.model-item { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 16px; background: var(--surface); }
.model-name { flex: 1; font-weight: 500; }
.model-id { font-size: 0.75rem; color: var(--text-soft); }
.switch { width: 46px; height: 26px; border-radius: var(--radius-full); border: none; background: #e8e3e6; cursor: pointer; position: relative; transition: background 0.25s; }
.switch.on { background: var(--primary-strong); }
.switch-dot { position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: #fff; transition: left 0.25s var(--ease-jelly); }
.switch.on .switch-dot { left: 23px; }
.panel-box { margin-top: 16px; background: var(--primary-bg); border-radius: var(--radius-lg); padding: 16px 20px; }
.panel-label { font-size: 0.75rem; color: var(--text-soft); }
.panel-value { font-weight: 600; margin-top: 4px; }

.api-module-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.api-module-card { background: var(--surface); border: none; border-radius: var(--radius-md); box-shadow: var(--shadow-card); padding: 16px; cursor: pointer; text-align: left; font-family: inherit; transition: all 0.2s var(--ease-jelly); }
.api-module-card:hover { transform: scale(1.04); }
.api-module-name { font-weight: 600; font-size: 0.9rem; }
.api-module-count { font-size: 0.75rem; color: var(--text-soft); margin-top: 4px; }
.api-list { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
.api-item { border-radius: 16px; background: var(--surface); overflow: hidden; }
.api-row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 14px; background: transparent; border: none; cursor: pointer; font-family: inherit; text-align: left; }
.method { border-radius: 8px; padding: 3px 10px; font-size: 0.7rem; font-weight: 600; flex-shrink: 0; }
.method--get { background: #dff5ef; color: #2d8a6b; }
.method--post { background: #e3ecff; color: #5b7bd5; }
.method--put { background: #fff3d6; color: #b8860b; }
.method--delete { background: #ffe3e3; color: #d05656; }
.api-path { font-weight: 500; font-size: 0.85rem; word-break: break-all; flex: 1; }
.api-summary { font-size: 0.75rem; color: var(--text-soft); }
.api-panel { padding: 14px; display: flex; flex-direction: column; gap: 10px; border-top: 2px dashed var(--primary-soft); }
.send-btn { align-self: flex-start; font-size: 0.8rem; }
.response-box { background: var(--surface); border: 2px solid var(--primary-soft); border-radius: 12px; padding: 10px; font-size: 0.72rem; font-family: monospace; max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0; }

.cc-input, .cc-textarea { width: 100%; border: 2px solid var(--primary-soft); border-radius: 14px; padding: 10px 12px; font-size: 0.85rem; color: var(--text); background: var(--surface); outline: none; font-family: inherit; transition: border-color 0.2s; }
.cc-input:focus, .cc-textarea:focus { border-color: var(--primary-strong); }
.cc-textarea { font-family: monospace; font-size: 0.78rem; resize: vertical; }


/* ===== 模型管理（9类型tab + 一键测试） ===== */
.model-type-tabs { flex-wrap: wrap; }
.provider-fields { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }
.provider-field-row { display: flex; align-items: center; gap: 10px; }
.provider-field-row .pf-label { width: 130px; flex-shrink: 0; font-size: 0.82rem; }
.provider-field-row .cc-input { flex: 1; }
.model-item { align-items: center; }
.model-main { flex: 1; min-width: 0; }
.model-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.model-test-result { font-size: 0.78rem; margin-top: 6px; word-break: break-all; }
.model-test-result.test-ok { color: #2d8a6b; }
.model-test-result.test-fail { color: #d05656; }
.mcp-test-report.mcp-test-ok { background: rgba(123,196,127,.12); }
.mcp-test-report.mcp-test-fail { background: rgba(227,109,109,.12); }

/* ===== 记忆视图切换/时间轴/图谱（移植原控制台） ===== */
.mem-view-switch { display: flex; gap: 6px; margin-left: auto; }
.mem-view-btn { padding: 6px 12px; font-size: 0.78rem; }
.mem-view-btn.is-on { background: var(--primary-strong); color: #fff; }
.mem-timeline-wrap { position: relative; max-height: 560px; overflow-y: auto; padding: 6px 4px; background: var(--surface); border-radius: var(--radius-lg); }
.mem-timeline-track { position: relative; padding-left: 18px; }
.mem-timeline-track::before {
  content: ''; position: absolute; left: 6px; top: 8px; bottom: 8px; width: 3px;
  border-radius: 3px; background: linear-gradient(180deg, #FF8FAB, #FFD86B, #9EE6D0); opacity: 0.5;
}
.mem-tl-group { margin-bottom: 18px; }
.mem-tl-date { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.mem-tl-date-dot { width: 13px; height: 13px; border-radius: 50%; background: #fff; border: 3px solid #FF8FAB; box-shadow: 0 0 8px rgba(255,143,171,.5); flex-shrink: 0; }
.mem-tl-date-text { font-weight: 600; font-size: 0.92rem; }
.mem-tl-date-count { font-size: 0.72rem; background: #fff0f5; color: #a08e96; border-radius: 9999px; padding: 1px 9px; }
.mem-tl-items { display: flex; flex-direction: column; gap: 8px; }
.mem-tl-item { background: #fff; border: 1px solid #ffd9e3; border-radius: 12px; padding: 10px 14px; }
.mem-tl-item--preference { border-left: 4px solid #FF8FAB; }
.mem-tl-item--profile { border-left: 4px solid #8FC7FF; }
.mem-tl-item--habit { border-left: 4px solid #FFD86B; }
.mem-tl-item--event { border-left: 4px solid #9EE6D0; }
.mem-tl-item--general { border-left: 4px solid #B8A9F5; }
.mem-tl-item-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.mem-tl-cat { font-size: 0.7rem; font-weight: 600; background: #fff0f5; border-radius: 9999px; padding: 1px 9px; }
.mem-tl-time { font-size: 0.74rem; color: #a08e96; font-family: monospace; }
.mem-tl-trust { font-size: 0.72rem; font-weight: 600; border: 1.5px solid; border-radius: 9999px; padding: 0 8px; }
.mem-tl-rc { font-size: 0.72rem; color: #d98a2b; }
.mem-tl-content { font-size: 0.86rem; line-height: 1.55; word-break: break-word; }
.mem-graph-wrap { background: var(--surface); border-radius: var(--radius-lg); padding: 12px; position: relative; }
.mem-graph-canvas { width: 100%; height: auto; display: block; }
.mem-graph-legend { display: flex; gap: 14px; justify-content: center; padding-top: 8px; font-size: 0.75rem; color: var(--text-soft); }
.legend-item { display: inline-flex; align-items: center; gap: 5px; }
.legend-item .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot--entity { background: #B8A9F5; }
.dot--fact { background: rgba(184,169,245,.75); }
.dot--hot { background: #FF8FAB; box-shadow: 0 0 6px rgba(255,143,171,.6); }

/* ===== 智能体编辑器-设备绑定 ===== */
.agent-bind-box { margin-top: 14px; }
.bind-code-row { display: flex; gap: 10px; }
.bind-code-input { flex: 1; letter-spacing: 0.3em; text-align: center; font-size: 1.05rem; }
.manual-add-details { margin-top: 12px; }
.manual-add-details summary { cursor: pointer; font-size: 0.85rem; color: var(--text-soft); }
.manual-add-details[open] summary { margin-bottom: 6px; }
.bound-device-list { margin-top: 8px; }
.field-hint { margin: 4px 0 0; font-size: 0.72rem; color: var(--text-soft); line-height: 1.4; }
.bind-empty-tip { color: var(--accent); }
/* ===== 主题选择器 ===== */
.theme-picker { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding: 10px 0 0; border-top: 1px dashed var(--primary-soft); }
.theme-picker-label { font-size: 0.72rem; color: var(--text-soft); }
.theme-swatches { display: flex; gap: 7px; flex-wrap: wrap; }
.theme-swatch { width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; transition: transform .2s var(--ease-jelly), border-color .2s; padding: 0; }
.theme-swatch:hover { transform: scale(1.18); }
.theme-swatch.is-active { border-color: var(--text); box-shadow: 0 0 0 2px var(--surface), 0 2px 8px rgba(0,0,0,.18); }
.bound-device-item {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px;
  border-radius: 12px; background: rgba(255,255,255,.6); margin-top: 6px;
}
.bound-device-name { font-weight: 500; font-size: 0.88rem; }
.bound-device-meta { flex: 1; font-size: 0.75rem; color: var(--text-soft); }

/* ===== 记忆管理 ===== */
.mem-agent-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.mem-agent-btn { padding: 8px 16px; font-size: 0.8rem; background: var(--surface); color: var(--text); border: 2px solid var(--primary-soft); }
.mem-agent-btn.is-on { background: var(--primary-strong); color: #fff; border-color: var(--primary-strong); }
.mem-toolbar { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.fact-list { display: flex; flex-direction: column; gap: 12px; }
.fact-card { background: var(--surface); border-radius: var(--radius-lg); padding: 18px 20px; }
.fact-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.fact-cat { border-radius: var(--radius-full); padding: 3px 12px; font-size: 0.72rem; font-weight: 500; background: #fff3d6; color: #b8860b; }
.fact-cat--preference { background: #ffe3ec; color: #d0568b; }
.fact-cat--profile { background: #e3ecff; color: #5b7bd5; }
.fact-cat--habit { background: #dff5ef; color: #2d8a6b; }
.fact-cat--event { background: #f3efff; color: #8b6fd5; }
.fact-cat--general { background: #f5f0eb; color: #8a7a6d; }
.fact-status { font-size: 0.72rem; color: #d05656; background: #ffe3e3; border-radius: var(--radius-full); padding: 3px 10px; }
.fact-date { margin-left: auto; font-size: 0.72rem; color: var(--text-soft); }
.fact-content { font-size: 0.95rem; font-weight: 500; margin-bottom: 10px; }
.fact-trust { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.trust-bar { flex: 1; max-width: 200px; height: 8px; border-radius: var(--radius-full); background: var(--primary-bg); overflow: hidden; }
.trust-fill { height: 100%; border-radius: var(--radius-full); background: linear-gradient(90deg, #FF8FAB, #F9A8D4); transition: width 0.4s var(--ease-out); }
.trust-num { font-size: 0.75rem; color: var(--text-soft); }
.fact-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.fact-btn { padding: 6px 14px; font-size: 0.78rem; }
.fact-del:hover { background: #ffe3e3; color: #d05656; border-color: #ffd0d0; }
.add-fact-box { margin-top: 20px; }
.add-fact-row { display: flex; gap: 10px; margin-top: 8px; }
.add-fact-row .cc-input { flex: 1; }

/* ===== 模态与新增页 ===== */
.modal-mask { position: fixed; inset: 0; background: rgba(75, 59, 68, 0.35); display: flex; align-items: center; justify-content: center; z-index: 9000; padding: 20px; }
.modal-card { width: 100%; max-width: 640px; max-height: 86vh; overflow-y: auto; }
.modal-title { font-size: 1.15rem; font-weight: 600; margin: 0 0 16px; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 12px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
.search-inline { display: flex; align-items: center; }
.search-inline .cc-input { width: 200px; }
.mono { font-family: 'Menlo', 'Consolas', monospace; font-size: 0.8rem; }

@media (max-width: 1199px) and (min-width: 900px) {
  .shell { gap: 16px; padding: 16px; }
  .sidebar { width: 200px; }
}

@media (max-width: 899px) {
  .sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 60;
    width: min(78vw, 300px); transform: translateX(-105%);
    transition: transform 0.25s ease; border-radius: 0 18px 18px 0;
    overflow-y: auto; height: 100vh;
  }
  .sidebar.is-open { transform: translateX(0); }
  .sidebar-mask {
    position: fixed; inset: 0; z-index: 55;
    background: rgba(60, 40, 80, 0.35); backdrop-filter: blur(2px);
  }
  .hamburger {
    position: fixed; left: 14px; top: 14px; z-index: 50;
    width: 42px; height: 42px; border-radius: 14px; border: none;
    background: var(--kawaii-primary, #d5a3ff); color: #fff;
    font-size: 1.2rem; cursor: pointer; box-shadow: 0 4px 14px rgba(160,90,255,.35);
  }
  .shell { padding: 68px 12px 12px; height: 100vh; }
  .api-summary { display: none; }
  .stat-grid, .agent-grid, .device-grid { grid-template-columns: 1fr 1fr; }
  .sim-stages { flex-direction: column; }
  .sim-arrow { transform: rotate(90deg); }
}

@media (min-width: 900px) {
  .hamburger { display: none; }
  .sidebar-mask { display: none !important; }
}

/* ===== 新增组件样式 ===== */
.menu-group { margin-bottom: 10px; }
.menu-group-label {
  font-size: 0.7rem; letter-spacing: 0.12em; opacity: 0.55;
  padding: 8px 12px 4px; text-transform: uppercase;
}
.compact-toggle { padding: 2px 8px; font-size: 0.75rem; margin-left: auto; }
.sidebar-head { display: flex; align-items: center; gap: 8px; }
.breadcrumb { font-size: 0.78rem; opacity: 0.6; margin-bottom: 10px; }

.shell--compact .fact-card, .shell--compact .agent-card, .shell--compact .device-card { padding: 8px 10px; }
.shell--compact .fact-content { font-size: 0.85rem; }
.shell--compact .page { gap: 10px; }

.sess-row { display: flex; align-items: center; gap: 8px; }
.sess-main { flex: 1; min-width: 0; }
.device-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.chat-agent-picker { display: flex; gap: 8px; align-items: center; }
.chat-agent-picker .select { width: auto; min-width: 140px; }

.mcp-address-row { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
.mcp-address { flex: 1; word-break: break-all; padding: 8px 10px; background: rgba(255,255,255,.6); border-radius: 10px; }
.mcp-tool-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-top: 10px; }
.mcp-tool-card { padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,.5); }
.mcp-tool-name { font-weight: 600; font-size: 0.9rem; }
.mcp-tool-desc { font-size: 0.78rem; opacity: 0.7; margin-top: 4px; }

.sim-stages { display: flex; align-items: stretch; gap: 8px; margin: 12px 0; }
.sim-stage {
  flex: 1; min-width: 0; padding: 12px 14px; border-radius: 14px;
  background: rgba(255,255,255,.55); border: 2px dashed rgba(160,120,220,.35);
  transition: border-color .2s, background .2s;
}
.sim-stage--loading { border-color: #f7b955; background: rgba(247,185,85,.12); }
.sim-stage--done { border-color: #7bc47f; border-style: solid; background: rgba(123,196,127,.10); }
.sim-stage--error { border-color: #e36d6d; border-style: solid; background: rgba(227,109,109,.10); }
.sim-stage-head { font-weight: 600; font-size: 0.9rem; margin-bottom: 6px; }
.sim-stage-body { font-size: 0.85rem; word-break: break-word; }
.sim-loading { opacity: .75; }
.sim-error { color: #c04d4d; }
.sim-hint { opacity: .5; }
.sim-arrow { align-self: center; font-size: 1.3rem; opacity: .5; }
.sim-input-row { display: flex; gap: 8px; }
.is-recording { animation: pulse-rec 1.2s infinite; background: #e36d6d !important; }
@keyframes pulse-rec { 0%,100% { box-shadow: 0 0 0 0 rgba(227,109,109,.5); } 50% { box-shadow: 0 0 0 8px rgba(227,109,109,0); } }
.sim-log {
  font-family: 'Menlo', 'Consolas', monospace; font-size: 0.75rem;
  white-space: pre-wrap; background: rgba(70,40,90,.06);
  border-radius: 10px; padding: 10px; max-height: 200px; overflow-y: auto;
}
.ota-upload-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ota-upload-row input[type="file"] { flex: 1; min-width: 200px; }
</style>
