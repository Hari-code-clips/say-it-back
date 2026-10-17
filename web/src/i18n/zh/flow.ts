// Chinese (Simplified) UI strings, part 2: the briefing flow.
// DRAFT: machine-written, NEEDS NATIVE-SPEAKER REVIEW before real use.
export const flow = {
  'start.title': '开始一次交底',
  'start.subtitle': '先选任务；如有作业许可，再填写；然后选工地和两种语言。', // v0.5.3 (F8): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'start.site': '工地',
  'start.languages': '语言',
  'start.youSpeak': '你说的语言',
  'start.workerHears': '工人听到的语言',
  'start.task': '任务',
  'start.taskHint': '每个任务都附带 SOP。也可以粘贴你自己的 SOP。',
  'start.changeTask': '更换任务', // v0.5.3 (follow-up): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'start.custom.title': '粘贴自己的 SOP',
  'start.custom.sub': '使用列表里没有的作业程序',
  'start.custom.short': '自定义 SOP',
  'start.custom.name': 'SOP 标题',
  'start.custom.nameShort': '请给 SOP 起一个简短的标题。',
  'start.custom.sop': 'SOP 内容',
  'start.custom.sopHint': '粘贴作业程序（至少 {min} 个字符）。你没有提到的步骤会被标出来。',
  // v0.5.2: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'start.permit': '作业许可（可选）',
  'start.permitOn': '属于作业许可',
  'start.permitHint': '每次交底一名工人。只有许可上的每名工人都得到“开工”，作业许可系统才会放行该许可。',
  'start.permitRef': '许可编号',
  'start.permitRefHelper': '按许可上的写法，例如 PTW-123。',
  'start.permitRefError': '请使用 1 至 32 个字母、数字或 . _ / -',
  'start.crewSize': '此许可上的工人数',
  'start.slot': '这次交底针对第几名工人',
  'start.noName': '不填姓名或编号：关于工人只记录这个序号。',
  // v0.5.3 (F8): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What is missing, shown beside a disabled Continue.
  'start.need.customTitle': '请给 SOP 起个标题',
  'start.need.customSop': '请粘贴 SOP 全文（至少 {min} 个字符）',
  'start.need.permitRef': '请输入许可编号',
  'start.need.permitRefInvalid': '请改正许可编号：字母、数字或 . _ / -',

  'instr.title': '你要向工人交代什么？',
  'instr.subtitle': '请用{lang}说出或输入你的指令，可以再修改。',
  'instr.label': '你的指令（{lang}）',
  'instr.helper': '针对这项任务写一两句话。',
  'instr.hold': '按住说话',
  'instr.starting': '正在启动麦克风…',
  'instr.listening': '正在聆听…松开发送',
  'instr.transcribing': '正在转写…',
  'instr.holdHint': '说话时按住按钮，说完松开。你说的话会显示在上方，可以修改。使用键盘时，按一次开始，再按一次停止。',
  'instr.tooShort': '时间太短了，请在说话时一直按住按钮。',
  'instr.transcribed': '已把你说的话加入指令。',
  'instr.useSample': '使用示例指令',
  'instr.find': '找出关键步骤',
  'instr.saving': '正在保存你的指令…',
  'instr.extracting': '正在对照 SOP 阅读你的指令…',
  'instr.extractingHint': '正在列出关键步骤及其危险。通常需要 15–40 秒。',
  'instr.need': '请先说出或输入你的指令', // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW

  'steps.title': '关键步骤',
  'steps.subtitle': '这些是工人必须清楚的步骤。你可以修改、删除或添加。在你确认之前，不会对工人说任何内容。',
  'steps.yourInstruction': '你的指令',
  'steps.editInstruction': '修改指令',
  'steps.conflicts': '与 SOP 冲突',
  'steps.conflictTitle': '你的指令与 SOP 冲突',
  'steps.conflictChip': '与 SOP 冲突',
  'steps.goToStep': '转到第 {n} 步',
  'steps.sopOnly': '来自 SOP，你的指令里没有', // v0.5.3 (F7): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'steps.sopOnlyHint': '保留它，就会向工人交底这一步；也可以删除。',
  'steps.sopQuote': '出自 {sop}。',
  'steps.notSpeakable': '无法用语音核对：请让工人现场演示',
  'steps.stepLabel': '第 {n} 步',
  'steps.textRequired': '请写明工人必须做什么。',
  // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What stops Confirm, shown beside it.
  'steps.need.none': '请至少添加一个步骤',
  'steps.need.text': '请写完每个步骤，或删除空的步骤',
  'steps.remove': '删除第 {n} 步',
  'steps.removed': '已删除该步骤',
  'steps.details': '危险与要点', // v0.5: as the English "Hazard and key points". DRAFT
  'steps.hazard': '危险',
  'steps.essential': '工人必须说到的内容',
  'steps.essentialHint': '每行一项。回答必须涵盖所有项。',
  'steps.add': '添加步骤',
  'steps.count': '{n} / {max} 个步骤',
  'steps.max': '最多只能有 {max} 个步骤。',
  'steps.empty': '还没有步骤',
  'steps.emptyHint': '请手动添加关键步骤，或重新读取指令。',
  'steps.extract': '找出关键步骤',
  'steps.confirm': '确认并生成话术',
  'steps.locked': '已在 {sop} 中确认。要修改步骤，需由安全主任确认一个新版本。', // security fixes A (H2): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'steps.writing': '正在撰写{lang}话术…',
  'steps.writingHint': '随后会由另一次独立检查把它翻译回来，让你读到工人将听到的内容。通常需要 15–40 秒。',

  // 16 Oct handover (F1-F3): script approval, the supervisor handover, the worker-only screens, the hand-back gate. ta and zh lines marked DRAFT need native-speaker review.
  'script.round': '第 {n} 轮，共 {max} 轮',
  'script.title': '核对话术', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.titleReexplain': '核对再次讲解', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.subtitle': '请用{supervisor}读一遍工人将听到的内容。在你点击下方按钮之前，不会对工人说任何内容。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.coverageOk': '每个步骤都已讲到并有对应提问',
  'script.coverageOkHint': '全部 {n} 个步骤都在话术中，且各有提问。',
  'script.coverageGap': '话术有缺口',
  'script.notDelivered': '指令中没有讲到：第 {steps} 步。',
  'script.notAsked': '没有任何提问涉及：第 {steps} 步。',
  'script.yourWords': '你的原话',
  'script.heardIn': '工人将听到的内容（{lang}）', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.heardInHint': '这是{worker}话术的独立翻译，方便你核对。工人听到的是{worker}原文，不是这段。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.deliversStep': '第 {n} 步',
  'script.questions': '将向工人提的问题',
  'script.questionsHint': '开放式问题，不会泄露答案。',
  'script.checks': '核对：',
  'script.stepN': '第 {n} 步',
  'script.closing': '结束语',
  'script.closingNoTranslation': '这句话没有{lang}翻译，无法在这里核对。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.workerText': '显示{worker}原文', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.workerTextHint': '语音会逐字读给工人听的内容。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.approve': '确认话术', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.approvalRecorded': '你已于 {time} 确认这份话术。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.toHandover': '前往交接', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.

  'brief.title': '交给工人',
  'brief.handoverBody': '工人会用{lang}听到指令并大声回答。你把手机交出去之后，屏幕只显示{lang}，只留给工人一个大按钮。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.mode': '交底方式',
  'brief.mode.live': '实时语音',
  'brief.mode.turn': '逐段播放',
  'brief.mode.liveHint': '实时对话：语音朗读话术并聆听回答。',
  'brief.mode.turnHint': '每一段使用录制语音。较慢，但实时语音不可用时仍能使用。',
  'brief.mode.liveUnlisted': 'Google 的实时语音尚未列出{lang}，所以这次讲解按段进行。仍可试用实时语音。', // 17 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'brief.give': '把手机交给工人', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exitInfo': '本轮进行中要停下来，请按住工人屏幕上方的锁形按钮 1.5 秒。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.kind': '交出手机前，先告诉工人：这不是考他们；说"我不太确定"也是好的回答。', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.backToScript': '返回话术',
  'brief.backToHandover': '返回交接', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exit': '按住结束本轮', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exitHint': '请继续按住 1.5 秒，结束本轮。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.leaveTitle': '结束这一轮？',
  'brief.leaveBody': '工人到目前为止的回答将被丢弃。你可以重新开始这一轮。',
  'brief.leaveConfirm': '结束本轮',
  'brief.supervisor': '我是主管', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorHint': '请继续按住 1.5 秒。只有主管才能把手机拿回去。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorTitle': '你是主管吗？', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorBody': '出了什么问题的详情是给主管看的，不是给工人看的。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorConfirm': '是，显示详情', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.holdToContinue': '主管：按住继续', // 16 Oct handover (F3, quiet held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneTitle': '手机回到你手里了吗？', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneBody': '核对结果是给主管看的，不是给工人看的。', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneConfirm': '是，手机在我手里', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.checking': '正在核对工人的回答…',
  'brief.checkingHint': '这几步按顺序进行。通常需要 15–40 秒。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.label': '核对步骤，按先后顺序', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s1': '不看步骤，把回答转写成文字', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s2': '两位独立评判阅读转写的文字', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s3': '用固定规则核查结果', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.note': '服务器不会告诉你现在进行到哪一步。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.failed': '语音会话已中断',
  'brief.failedTurnHint': '你可以改用逐段播放来完成同一轮。',
  'brief.useTurn': '改用逐段播放',
  'brief.submitFailed': '回答已录下，但暂时无法核对',
  'brief.notRecordedHint': '逐段播放会重新朗读话术，并以服务器可以核对的方式录下回答。',
  'brief.err.connect_failed': '无法建立实时语音连接。',
  'brief.err.socket_closed': '实时语音连接已断开。',
  'brief.err.timeout': '实时语音服务没有响应。',
  'brief.err.protocol': '实时语音服务返回了意外内容。',
  'brief.err.bad_ticket': '实时语音连接未被接受，请重试。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.err.bad_message': '实时语音服务拒绝了一条消息。',
  'brief.err.invalid_state': '这一轮现在无法开始语音会话。',
  'brief.err.limit': '这一轮已达到实时语音的上限。',
  'brief.err.upstream_busy': '语音服务繁忙，请稍后再试。',
  'brief.err.tts_failed': '无法准备录制语音。',
  'brief.err.aborted': '本轮已结束。',
  'brief.err.unknown': '语音会话失败。',
  'brief.err.submit': '服务器无法核对回答。请重试；录音仍保存在本设备上。',
  'brief.sample.label': '本轮使用存储的示例回答', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.checking': '正在查找存储的示例回答…', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.all': '每道题都有存储的示例回答。没有人需要说{lang}。', // 16 Oct, every question has a sample (build-notes/30): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.has': '第 {list} 题有存储的示例回答。', // 16 Oct (build-notes/30): the first sentence of the earlier line. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.hasMany': '第 {list} 题有存储的示例回答。', // 16 Oct (build-notes/30): Chinese has no plural, so as has. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.synthetic': '它是合成语音，不是工人本人，结果页会把它标为示例。', // 16 Oct (build-notes/30): the second sentence of the earlier line. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.syntheticMany': '它们是合成语音，不是工人本人，结果页会把它们标为示例。', // 16 Oct (build-notes/30): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.rest': '其余的题目由工人用语音回答。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.stepsLeft': '有些步骤不在任何存储的回答里，所以可能还需要再问一轮。', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.none': '这个任务、语言和轮次没有存储的示例回答。每个问题都由工人用语音回答。', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.failed': '示例回答无法播放，工人改用语音回答了。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.dropped': '示例回答到得太晚，没有用于那道题。',
  'brief.reportHeld': '工人的问题报告还没有发出',
  'brief.reportHeldHint': '请用本屏幕上工人的按钮重新发送或删除它，然后才会显示结果。', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.reportHoldsPage': '有一条问题报告还没有发出。请先发送或删除它。',

  'result.title': '第 {n} 轮结果',
  'result.subtitle': '每个步骤都显示工人复述了什么。核对的是回答，不是人。',
  'result.announce': '第 {n} 轮已核对。仍未完成的步骤：{open} 个。',
  'result.glance': '一览',
  'result.steps': '关键步骤',
  'result.stepN': '第 {n} 步',
  'result.hazard': '危险：{hazard}',
  'result.workerSaid': '工人说（{lang}）',
  'result.sampleSaid': '存储的示例回答说（{lang}）', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'result.inLang': '{lang}译文',
  'result.why': '原因：',
  'result.noMention': '回答没有提到这一步。',
  'result.notClear': '不够清楚，不能算数。请再问一次。',
  'result.noQuote': '这一步没有记录引文。',
  'result.earlier': '前几轮已说到',
  'result.answers': '工人说了什么',
  'result.answersHint': '{lang}原话，附翻译。',
  'result.question': '问题 {n}',
  'result.play': '播放回答 {n}',
  'result.stop': '停止',
  'result.noSpeech': '没有听到语音。',
  'result.modelRefused': '核对器无法处理这个回答。请再问一次，或当面核实。', // v0.5.1: DRAFT
  'result.noTranscript': '这个问题没有转写。',
  'result.detected': '听到的语言：{lang}',
  'result.otherLang': '其他语言',
  'result.exhausted': '仍有步骤未完成',
  'result.exhaustedHint': '{max} 轮之后，请让工人现场演示来核实这些步骤。',
  'result.sample': '示例回答（合成语音）',
  'result.deliveryWhy': '为什么“再问一次”：语音偏离了脚本',
  'result.deliveryWhyGeneric': '这一步的内容，语音没有按你确认的脚本说。',
  'result.deliveryWhyHint': '工人听到的可能与你的脚本不同，所以这一步要再问一次才算数。请再讲解一遍。', // v0.5.3: DRAFT
  'result.deliveryWhyEarlier': '这发生在关于这一步的问题之前，所以工人可能已经听到了提示。',
  // v0.5.3 (F4): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What to do when the two judges split.
  'result.disagreedAsk': '两项核对结果不一致，所以这一步显示为“再问一次”。请先听这段回答，再重新讲解这一步，或当面核对。',
  'result.disagreedWrong': '两项核对结果不一致，其中一项发现回答与这一步相反，所以显示为“说错”。决定之前请先听这段回答。',
  'result.reexplain': '再次讲解未完成的步骤',
  'result.decide': '决定：开工或暂不开工', // v0.5.3 (F7): one decide label. DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'delivery.title': '语音没有照你的脚本说',
  'delivery.hint': '代码会把语音说的话与确认的脚本比对。下面这些部分所传达或提问的步骤，即使回答说到了，也会标为“再问一次”。',
  'delivery.said': '语音说的（{lang}）',
  'delivery.script': '你确认的脚本',
  'delivery.instruction': '指令',
  'delivery.closing': '结束语',
  'delivery.question': '第 {n} 题',
  'delivery.not_spoken': '语音没有说{what}。',
  'delivery.wrong_script': '语音用了别的语言说{what}。',
  'delivery.low_similarity': '语音说{what}时，用词与你的脚本不同。',
  'delivery.number_changed': '{what}里的一个数字变了。',
  'delivery.negation_dropped': '语音在{what}里漏掉了一个“不”。',
  'delivery.negation_added': '语音在{what}里多加了一个“不”。',
  'delivery.negation_changed': '{what}里的一个“不”变了。',
  'delivery.reply_too_long': '在第 {n} 题之后，语音说的不只是一句谢谢。',
  'delivery.reply_not_neutral': '在第 {n} 题之后，语音说了脚本里的词，而不只是一句谢谢。',
  'delivery.mismatch': '语音在{what}说的内容与你的脚本不符。',
  'models.title': '是什么核对了这些回答',
  'models.unknown': '未记录',
  'models.transcribe': '盲转写',
  'models.transcribeHint': '在看不到步骤的情况下，写下工人说的话。',
  'models.judgeA': '评判 A',
  'models.judgeAHint': '听录音，并阅读转写。',
  'models.judgeB': '评判 B',
  'models.judgeBHint': '只读转写，使用与评判 A 不同的模型。',
  'models.judgeBSame': '只读转写，使用与评判 A 相同的模型。',
  'models.guard': '守护规则',
  'models.guardValue': '代码，不用模型',
  // v0.5.3 (F7): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. The old text said the worse verdict wins; that rule ended in v0.5.3.
  'models.guardHint': '做最后判定。两位评判一致时，以一致的结论为准；任何一位发现回答与步骤相反，以此为准；其他不一致一律为“再问一次”，绝不会是“已说到”。引文必须确实出现在转写中。',
  'hazard.title': '工人报告的问题（{n}）',
  'hazard.hint': '每个问题都写下处理记录之前，“开工”保持锁定。',
  'hazard.card': '问题 {n}',
  'hazard.open': '尚未处理',
  'hazard.acked': '已处理',
  'hazard.during': '第 {n} 轮中报告，{time}',
  'hazard.tap': '工人按了“报告问题”，但没有说话。请问问他哪里有问题。',
  'hazard.said': '工人说的（{lang}）',
  'hazard.noWords': '录音里没有说话内容。请问问工人哪里有问题。',
  'hazard.ackedBy': '处理记录：{by}，{time}',
  'hazard.ackedAt': '处理记录：{time}',
  'hazard.noteLabel': '你对此做了什么？',
  'hazard.noteHint': '至少 {min} 个字，会随交底一起记录。',
  'hazard.noteShort': '请至少写 {min} 个字。',
  'hazard.ack': '记录处理措施',
  'hazard.ackDone': '问题 {n} 的处理记录已保存。',
  'hazard.announce': '工人报告的问题：{n} 个。',
  // v0.5.3 (F4): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. The compact banner that jumps to the note.
  'hazard.banner': '工人报告了一个问题 · 写下你的处理措施之前，“开工”保持锁定',
  'hazard.bannerMany': '工人报告了 {n} 个问题 · 写下你的处理措施之前，“开工”保持锁定',
  'hazard.bannerAction': '写下处理措施',

  'reexplain.title': '再次讲解未完成的步骤',
  // v0.5.3 (F6): the subtitle is now the first sentence only, so both choices fit above the bar; the second moved to the open steps. DRAFT.
  'reexplain.subtitle': '选择工人再听一遍的方式。',
  'reexplain.openHint': '之后只针对这些步骤提新的问题。',
  'reexplain.kind': '没有说回来的步骤，要换一种讲法，而不是把同样的话说得更大声。能的话，把实物指给对方看。', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'reexplain.open': '未完成的步骤（{n}）',
  'reexplain.how': '用什么方式讲解？',
  'reexplain.generate': '针对性的再次讲解',
  'reexplain.generateHint': '用{lang}对未完成的步骤做简短、简单的再次讲解。工人听到之前你可以先看。',
  'reexplain.own': '用我自己的话',
  'reexplain.ownHint': '用你的语言输入，会翻译成{lang}给工人听。',
  'reexplain.ownLabel': '你的再次讲解',
  'reexplain.write': '撰写再次讲解', // v0.5.3 (F6): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'reexplain.busy': '正在撰写{lang}的再次讲解和新问题…',
  'reexplain.need': '请先输入你的再次讲解', // v0.5.3 (F6): DRAFT, NEEDS NATIVE-SPEAKER REVIEW

  'decision.title': '你的决定',
  'decision.subtitle': '工具核对了工人的复述。是否开工由你决定。',
  'decision.checked': '核对情况',
  'decision.rounds': '已进行轮数：{n}',
  'decision.openTitle': '仍有未完成的步骤：{n} 个',
  'decision.openHint': '如果仍然开工，请写明原因。原因会随你的决定一起记录。',
  'decision.choose': '开工或暂不开工',
  'decision.go': '开工',
  'decision.goHint': '可以开始工作。',
  'decision.goLocked': '工人报告的每个问题都写下处理记录之前，此项锁定。',
  'decision.sampleOpen': '只由存储的示例回答说到的步骤算作未完成：工人本人没有说。',
  'decision.noGo': '暂不开工',
  'decision.noGoHint': '工作暂时不开始。',
  'decision.reason': '原因（可选）',
  'decision.reasonRequired': '原因（必填）',
  'decision.reasonHint': '至少 {min} 个字符。请说明为什么仍有未完成步骤也可以开工。',
  'decision.reasonHintSample': '至少 {min} 个字符。由存储的示例回答说出的步骤仍算未完成，因为工人本人没有说。请说明为什么可以开工。', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'decision.reasonShort': '请至少写 {min} 个字符。',
  'decision.by': '你的姓名或缩写（可选）',
  'decision.byHint': '随决定一起记录。绝不是工人姓名。',
  'decision.record': '记录决定',
  // v0.5.3 (F5): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. Why Record decision is off, and the confirm before it.
  'decision.need.choice': '请选择“开工”或“暂不开工”',
  'decision.need.reason': '请写明仍有未完成步骤时为什么可以开工',
  'decision.need.hazard': '请写下你对工人所报问题的处理措施',
  'decision.backToResult': '返回结果',
  'decision.confirm.title': '记录“{value}”？',
  'decision.confirm.body': '这是最终决定，记录之后不能修改。',
  'decision.confirm.open': '仍有未完成的步骤：{n} 个。你写的原因会随决定一起记录。',
  'decision.confirm.noGoKind': '“暂不开工”不是工人的过错。你可以在记录页再给对方讲一遍。', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'decision.confirm.cancel': '继续修改',
  'decision.confirm.go': '记录“开工”',
  'decision.confirm.noGo': '记录“暂不开工”',

  'record.title': '交底记录',
  'record.subtitle': '核对了什么，你做了什么决定。',
  'record.new': '开始新的交底',
  'record.all': '全部记录',
  'record.by': '决定人：{by}',
  'record.reason': '原因',
  'record.openAtDecision': '决定时仍未完成的步骤：{n} 个',
  'record.checked': '核对情况',
  'record.open': '决定时未完成',
  'record.rounds': '各轮情况',
  'record.roundN': '第 {n} 轮',
  'record.initial': '首次交底',
  'record.reexplain': '再次讲解',
  'record.meta': '交底信息：',
  'record.note': '本记录只显示核对了什么以及你的决定，不对工人打分，也不保存工人的姓名、编号或录音。',
  // v0.5.2: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'record.permit': '作业许可',
  'record.nextWorker': '为工人 {n}/{m} 交底',
  'record.nextWorkerHint': '此许可上的下一位：第 {n} 名工人，共 {m} 名。工地、任务、语言和许可不变；指令已填好，可以修改。',
  'record.permitLast': '第 {m} 名工人，共 {m} 名，这是此许可上的最后一名。是否放行由作业许可系统决定：每名工人都需要“开工”。',
  'record.mockBoard': '模拟许可看板：{crew} 名工人中 {verified} 名为“开工” · {status}',
  'record.hazardsAtDecision': '决定时尚未处理的问题：{n}',
  // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW. After a No-go on a permit: the same worker again on the same permit.
  'record.decisionTitle': '决定',
  'record.rebrief': '再次为工人 {n} 交底',
  'record.rebriefHint': '第 {n} 名工人（共 {m} 名）为“暂不开工”。许可上每名工人都得到“开工”才会放行，作业许可系统保留每名工人最新的决定。你可以在同一许可上再次为这名工人交底。',
  'chain.title': '防篡改核查',
  'chain.how': '这次交底的每一次变更都是 SHA-256 链上的一环，把步骤、脚本、评定和决定绑定在一起。服务器会重新计算整条链。',
  'chain.checking': '正在核查记录链…',
  'chain.failed': '暂时无法核查记录链。',
  'chain.ok': '记录已核验 · {n} 个事件 · 链条完整',
  'chain.head': '链头',
  'chain.broken': '这份记录与它的链不一致',
  'chain.brokenAt': '核查在第 {seq} 个事件（{type}）处失败。',
  'chain.refused': '决定之后的修改会被拒绝。',
  'chain.samples': '存储的示例回答',
  'chain.noSamples': '这次交底没有使用存储的示例回答。',
  'chain.sampleLine': '第 {round} 轮，第 {q} 题：存储的合成语音，不是工人本人',
  'chain.timeline': '事件（{n}）',
  'chain.none': '这份记录建于防篡改核查之前，没有可核查的链。',
  'chain.reason.seq_mismatch': '有事件缺失或顺序不对。',
  'chain.reason.prev_hash_mismatch': '有事件没有接上前一个事件。',
  'chain.reason.hash_mismatch': '有事件的哈希与记录值不符。',
  'chain.reason.instruction_mismatch': '指令与记录的不一致。',
  'chain.reason.sop_mismatch': 'SOP 与记录的不一致。',
  'chain.reason.steps_mismatch': '步骤与记录的不一致。',
  'chain.reason.script_mismatch': '某一轮的脚本与记录的不一致。',
  'chain.reason.ratings_mismatch': '某一轮的评定与记录的不一致。',
  'chain.reason.round_missing': '记录过的一轮不见了。',
  'chain.reason.hazard_mismatch': '报告的问题与记录的不一致。',
  'chain.reason.hazard_missing': '报告的问题不见了。',
  'chain.reason.decision_mismatch': '决定与记录的不一致。',
  'chain.reason.record_hash_mismatch': '记录的哈希不是最后一个事件的哈希。',
  'chain.reason.unrecorded_change': '记录里有一处没有任何事件记载的修改。',
  'chain.reason.other': '记录在写入之后被改动过。',
  'event.created': '创建交底',
  'event.instruction_edited': '修改指令',
  'event.steps_proposed': '列出关键步骤',
  'event.steps_confirmed': '确认步骤',
  'event.round_created': '为第 {n} 轮写出脚本',
  'event.script_approved': '确认第 {n} 轮脚本',
  'event.round_judged': '核对第 {n} 轮回答',
  'event.hazard_raised': '报告问题 {n}',
  'event.hazard_acknowledged': '处理问题 {n}',
  'event.decided': '记录决定',
}
