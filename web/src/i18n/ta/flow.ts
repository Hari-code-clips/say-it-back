// Tamil UI strings, part 2: the briefing flow.
// DRAFT: machine-written, NEEDS NATIVE-SPEAKER REVIEW before real use.
export const flow = {
  'start.title': 'பிரீஃபிங்கைத் தொடங்குங்கள்',
  'start.subtitle': 'பணியைத் தேர்ந்தெடுங்கள்; வேலை அனுமதி இருந்தால் சேருங்கள்; பிறகு தளத்தையும் இரண்டு மொழிகளையும் தேர்ந்தெடுங்கள்.', // v0.5.3 (F8): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'start.site': 'தளம்',
  'start.languages': 'மொழிகள்',
  'start.youSpeak': 'நீங்கள் பேசுவது',
  'start.workerHears': 'தொழிலாளர் கேட்பது',
  'start.task': 'பணி',
  'start.taskHint': 'ஒவ்வொரு பணிக்கும் அதன் SOP உண்டு. அல்லது உங்கள் சொந்த SOP-ஐ ஒட்டுங்கள்.',
  'start.changeTask': 'பணியை மாற்று', // v0.5.3 (follow-up): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'start.custom.title': 'சொந்த SOP-ஐ ஒட்டுங்கள்',
  'start.custom.sub': 'பட்டியலில் இல்லாத நடைமுறையைப் பயன்படுத்துங்கள்',
  'start.custom.short': 'சொந்த SOP',
  'start.custom.name': 'SOP தலைப்பு',
  'start.custom.nameShort': 'SOP-க்கு ஒரு சிறிய தலைப்பு கொடுங்கள்.',
  'start.custom.sop': 'SOP உரை',
  'start.custom.sopHint': 'நடைமுறையை ஒட்டுங்கள் (குறைந்தது {min} எழுத்துகள்). நீங்கள் குறிப்பிடாத படிகள் குறிக்கப்படும்.',
  // v0.5.2: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'start.permit': 'வேலை அனுமதி (விருப்பம்)',
  'start.permitOn': 'வேலை அனுமதிக்கானது',
  'start.permitHint': 'ஒரு பிரீஃபிங்கில் ஒரு தொழிலாளர். அனுமதியில் உள்ள ஒவ்வொருவருக்கும் Go கிடைத்த பிறகே அனுமதி அமைப்பு அனுமதியை விடுவிக்கும்.',
  'start.permitRef': 'அனுமதி எண்',
  'start.permitRefHelper': 'அனுமதியில் உள்ளபடி, எ.கா. PTW-123.',
  'start.permitRefError': '1 முதல் 32 எழுத்துகள், எண்கள் அல்லது . _ / - பயன்படுத்துங்கள்',
  'start.crewSize': 'இந்த அனுமதியில் உள்ள தொழிலாளர்கள்',
  'start.slot': 'இந்தப் பிரீஃபிங் எந்தத் தொழிலாளருக்கு',
  'start.noName': 'பெயரோ அடையாள எண்ணோ வேண்டாம்: தொழிலாளரைப் பற்றிப் பதிவாவது இந்த எண் மட்டுமே.',
  // v0.5.3 (F8): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What is missing, shown beside a disabled Continue.
  'start.need.customTitle': 'SOP-க்கு ஒரு தலைப்பு கொடுங்கள்',
  'start.need.customSop': 'SOP உரையை ஒட்டுங்கள் (குறைந்தது {min} எழுத்துகள்)',
  'start.need.permitRef': 'அனுமதி எண்ணை உள்ளிடுங்கள்',
  'start.need.permitRefInvalid': 'அனுமதி எண்ணைச் சரிசெய்யுங்கள்: எழுத்துகள், எண்கள் அல்லது . _ / -',

  'instr.title': 'தொழிலாளருக்கு என்ன சொல்கிறீர்கள்?',
  'instr.subtitle': 'உங்கள் அறிவுறுத்தலை {lang} மொழியில் பேசுங்கள் அல்லது தட்டச்சு செய்யுங்கள். திருத்தலாம்.',
  'instr.label': 'உங்கள் அறிவுறுத்தல் ({lang})',
  'instr.helper': 'இந்தப் பணியைப் பற்றி ஒன்று அல்லது இரண்டு வாக்கியங்கள்.',
  // v0.5: these labels are shortened to keep one line on a 320 px phone. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'instr.hold': 'பேச அழுத்திப் பிடி',
  'instr.starting': 'மைக் தொடங்குகிறது…',
  'instr.listening': 'விட்டால் அனுப்பும்', // "sends when you let go": the ring shows it is listening. DRAFT
  'instr.transcribing': 'எழுத்தாக்குகிறது…',
  'instr.holdHint': 'பேசும்போது பொத்தானை அழுத்திப் பிடித்து, பிறகு விடுங்கள். உங்கள் சொற்கள் மேலே தோன்றும்; திருத்தலாம். விசைப்பலகையில் ஒருமுறை அழுத்தித் தொடங்கி, மீண்டும் அழுத்தி நிறுத்துங்கள்.',
  'instr.tooShort': 'மிகவும் குறுகியது. பேசும்போது பொத்தானை அழுத்திப் பிடியுங்கள்.',
  'instr.transcribed': 'உங்கள் சொற்கள் அறிவுறுத்தலில் சேர்க்கப்பட்டன.',
  'instr.useSample': 'மாதிரியைப் பயன்படுத்து', // v0.5: shortened (one line at 320 px). DRAFT
  'instr.find': 'முக்கியப் படிகளை எடு', // v0.5: shortened to keep one line at 320 px. DRAFT
  'instr.saving': 'உங்கள் அறிவுறுத்தலைச் சேமிக்கிறது…',
  'instr.extracting': 'SOP-உடன் உங்கள் அறிவுறுத்தலைப் படிக்கிறது…',
  'instr.extractingHint': 'முக்கியப் படிகளும் அவற்றின் ஆபத்துகளும் பட்டியலிடப்படுகின்றன. வழக்கமாக 15–40 வினாடிகள் ஆகும்.',
  'instr.need': 'முதலில் உங்கள் அறிவுறுத்தலைச் சொல்லுங்கள் அல்லது தட்டச்சு செய்யுங்கள்', // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW

  'steps.title': 'முக்கியப் படிகள்',
  'steps.subtitle': 'தொழிலாளருக்குத் தெளிவாகத் தெரிய வேண்டிய படிகள் இவை. படிகளைத் திருத்தலாம், நீக்கலாம், சேர்க்கலாம். நீங்கள் உறுதிசெய்யும் வரை தொழிலாளரிடம் எதுவும் பேசப்படாது.',
  'steps.yourInstruction': 'உங்கள் அறிவுறுத்தல்',
  'steps.editInstruction': 'அறிவுறுத்தலைத் திருத்து',
  'steps.conflicts': 'SOP-உடன் முரண்பாடுகள்',
  'steps.conflictTitle': 'உங்கள் அறிவுறுத்தல் SOP-உடன் முரண்படுகிறது',
  'steps.conflictChip': 'SOP-உடன் முரண்',
  'steps.goToStep': 'படி {n}-க்குச் செல்',
  'steps.sopOnly': 'SOP-இல் உள்ளது, உங்கள் அறிவுறுத்தலில் இல்லை', // v0.5.3 (F7): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'steps.sopOnlyHint': 'தொழிலாளருக்கு விளக்க வைத்துக்கொள்ளுங்கள், அல்லது நீக்குங்கள்.',
  'steps.sopQuote': '{sop}-இலிருந்து.',
  'steps.notSpeakable': 'குரலால் சரிபார்க்க முடியாது: செய்து காட்டச் சொல்லிச் சரிபாருங்கள்',
  'steps.stepLabel': 'படி {n}',
  'steps.textRequired': 'தொழிலாளர் செய்ய வேண்டியதை எழுதுங்கள்.',
  // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What stops Confirm, shown beside it.
  'steps.need.none': 'குறைந்தது ஒரு படியைச் சேர்க்கவும்',
  'steps.need.text': 'ஒவ்வொரு படியையும் எழுதுங்கள், அல்லது காலியானதை நீக்குங்கள்',
  'steps.remove': 'படி {n}-ஐ நீக்கு',
  'steps.removed': 'படி நீக்கப்பட்டது',
  'steps.details': 'ஆபத்து, முக்கியவை', // v0.5: shortened (one line). DRAFT
  'steps.hazard': 'ஆபத்து',
  'steps.essential': 'தொழிலாளர் சொல்ல வேண்டியவை',
  'steps.essentialHint': 'ஒரு வரிக்கு ஒன்று. பதில் எல்லாவற்றையும் உள்ளடக்க வேண்டும்.',
  'steps.add': 'படியைச் சேர்',
  'steps.count': '{max}-இல் {n} படிகள்',
  'steps.max': 'அதிகபட்சம் {max} படிகள் வைக்கலாம்.',
  'steps.empty': 'இன்னும் படிகள் இல்லை',
  'steps.emptyHint': 'முக்கியப் படிகளைக் கையால் சேருங்கள், அல்லது அறிவுறுத்தலை மீண்டும் படிக்க வையுங்கள்.',
  'steps.extract': 'முக்கியப் படிகளை எடு', // v0.5: as instr.find. DRAFT
  'steps.confirm': 'உறுதிசெய்து எழுது', // v0.5: shortened (one line). DRAFT
  'steps.locked': '{sop}-இல் உறுதிசெய்யப்பட்டது. ஒரு படியை மாற்ற, பாதுகாப்பு அலுவலர் புதிய பதிப்பை உறுதிசெய்ய வேண்டும்.', // security fixes A (H2): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'steps.writing': '{lang} ஸ்கிரிப்டை எழுதுகிறது…',
  'steps.writingHint': 'பிறகு, தொழிலாளர் கேட்பதை நீங்கள் படிக்க, தனிச் சரிபார்ப்பு அதை மீண்டும் மொழிபெயர்க்கிறது. வழக்கமாக 15–40 வினாடிகள் ஆகும்.',

  // 16 Oct handover (F1-F3): script approval, the supervisor handover, the worker-only screens, the hand-back gate. ta and zh lines marked DRAFT need native-speaker review.
  'script.round': 'சுற்று {n} / {max}',
  'script.title': 'ஸ்கிரிப்டைச் சரிபாருங்கள்', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.titleReexplain': 'மறு விளக்கத்தைச் சரிபாருங்கள்', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.subtitle': 'தொழிலாளர் கேட்கப்போவதை {supervisor} மொழியில் படியுங்கள். கீழே உள்ள பொத்தானை அழுத்தும் வரை தொழிலாளரிடம் எதுவும் பேசப்படாது.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.coverageOk': 'ஒவ்வொரு படியும் சொல்லப்பட்டு, கேள்வியும் உள்ளது',
  'script.coverageOkHint': 'மொத்தம் {n} படிகளும் ஸ்கிரிப்டில் உள்ளன; ஒவ்வொன்றுக்கும் கேள்வி உண்டு.',
  'script.coverageGap': 'ஸ்கிரிப்டில் இடைவெளி உள்ளது',
  'script.notDelivered': 'அறிவுறுத்தலில் சொல்லப்படாத படி: {steps}.',
  'script.notAsked': 'எந்தக் கேள்வியும் கேட்காத படி: {steps}.',
  'script.yourWords': 'உங்கள் சொற்கள்',
  'script.heardIn': 'தொழிலாளர் கேட்கப்போவது, {lang} மொழியில்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.heardInHint': '{worker} ஸ்கிரிப்டின் தனி மொழிபெயர்ப்பு; நீங்கள் சரிபார்க்க. தொழிலாளர் கேட்பது {worker} உரையை, இதை அல்ல.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.deliversStep': 'படி {n}',
  'script.questions': 'தொழிலாளரிடம் கேட்கப்படும் கேள்விகள்',
  'script.questionsHint': 'திறந்த கேள்விகள். எதுவும் பதிலைச் சொல்லிவிடாது.',
  'script.checks': 'சரிபார்ப்பது:',
  'script.stepN': 'படி {n}',
  'script.closing': 'நிறைவு வரி',
  'script.closingNoTranslation': 'இந்த வரிக்கு {lang} மொழிபெயர்ப்பு இல்லை; இங்கே சரிபார்க்க முடியாது.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.workerText': '{worker} உரையைக் காட்டு', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.workerTextHint': 'குரல் தொழிலாளருக்கு அப்படியே படிப்பது.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.approve': 'ஸ்கிரிப்டை உறுதிசெய்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.approvalRecorded': 'இந்த ஸ்கிரிப்டை {time}-க்கு உறுதிசெய்தீர்கள்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'script.toHandover': 'ஒப்படைப்புக்குச் செல்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.

  'brief.title': 'தொழிலாளரிடம் ஒப்படையுங்கள்',
  'brief.handoverBody': 'தொழிலாளர் {lang} மொழியில் அறிவுறுத்தலைக் கேட்டு, சத்தமாகப் பதில் சொல்வார். போனைக் கொடுத்ததும் திரையில் {lang} மட்டுமே தெரியும்; தொழிலாளருக்கு ஒரே ஒரு பெரிய பொத்தான் இருக்கும்.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.mode': 'பிரீஃபிங் முறை',
  'brief.mode.live': 'நேரடிக் குரல்',
  'brief.mode.turn': 'ஒவ்வொரு பகுதியாக',
  'brief.mode.liveHint': 'நேரடி உரையாடல்: குரல் ஸ்கிரிப்டைப் படித்துக் கேட்கும்.',
  'brief.mode.turnHint': 'ஒவ்வொரு பகுதிக்கும் பதிவு செய்யப்பட்ட குரல். மெதுவானது; நேரடிக் குரல் வேலை செய்யாவிட்டால் உதவும்.',
  'brief.mode.liveUnlisted': 'நேரடிக் குரலுக்கு {lang} மொழியை Google இன்னும் பட்டியலிடவில்லை; அதனால் இந்த விளக்கம் ஒவ்வொரு பகுதியாகத் தொடங்கும். நேரடிக் குரலையும் முயலலாம்.', // 17 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'brief.give': 'தொழிலாளரிடம் கொடு', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exitInfo': 'சுற்றின் நடுவே நிறுத்த, தொழிலாளர் திரையின் மேலே உள்ள பூட்டுப் பொத்தானை 1.5 வினாடி அழுத்திப் பிடியுங்கள்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.kind': 'போனைக் கொடுக்கும் முன் தொழிலாளரிடம் சொல்லுங்கள்: இது அவருக்கான தேர்வு அல்ல; "சரியாகத் தெரியவில்லை" என்பதும் நல்ல பதில்தான்.', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.backToScript': 'ஸ்கிரிப்டுக்குத் திரும்பு',
  'brief.backToHandover': 'ஒப்படைப்புக்குத் திரும்பு', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exit': 'முடிக்கப் பிடியுங்கள்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.exitHint': 'சுற்றை முடிக்க 1.5 வினாடி பிடித்திருங்கள்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.leaveTitle': 'இந்தச் சுற்றை முடிக்கவா?',
  'brief.leaveBody': 'இதுவரை தொழிலாளர் சொன்ன பதில்கள் நீக்கப்படும். சுற்றை மீண்டும் தொடங்கலாம்.',
  'brief.leaveConfirm': 'சுற்றை முடி',
  'brief.supervisor': 'நான் மேற்பார்வையாளர்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorHint': '1.5 வினாடி பிடித்திருங்கள். போனை மேற்பார்வையாளர் மட்டுமே திரும்ப எடுப்பார்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorTitle': 'நீங்கள் மேற்பார்வையாளரா?', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorBody': 'என்ன தவறு நடந்தது என்ற விவரம் மேற்பார்வையாளருக்கு; தொழிலாளருக்கு அல்ல.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.supervisorConfirm': 'ஆம், விவரத்தைக் காட்டு', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.holdToContinue': 'மேற்பார்வையாளர்: பிடிக்கவும்', // 16 Oct handover (F3, quiet held button): "Supervisor: hold", the longer "hold to continue" is two lines at 320 px. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneTitle': 'போன் உங்களிடம் திரும்பி வந்ததா?', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneBody': 'சரிபார்ப்பின் முடிவு மேற்பார்வையாளருக்கு; தொழிலாளருக்கு அல்ல.', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.haveThePhoneConfirm': 'ஆம், போன் என்னிடம் உள்ளது', // 16 Oct handover (F3, held button): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.checking': 'தொழிலாளர் சொன்னதைச் சரிபார்க்கிறது…',
  'brief.checkingHint': 'இவை இந்த வரிசையில் நடக்கும். வழக்கமாக 15–40 வினாடிகள் ஆகும்.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.label': 'சரிபார்ப்பு, வரிசைப்படி', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s1': 'படிகளைக் காட்டாமல் பதில்கள் எழுத்தாக்கப்படுகின்றன', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s2': 'இரண்டு தனி மதிப்பீட்டாளர்கள் எழுதியதைப் படிக்கிறார்கள்', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.s3': 'நிலையான விதிகள் முடிவைச் சரிபார்க்கின்றன', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.check.note': 'இவற்றில் எது நடக்கிறது என்பதை சர்வர் சொல்வதில்லை.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.failed': 'குரல் அமர்வு நின்றுவிட்டது',
  'brief.failedTurnHint': 'அதே சுற்றை ஒவ்வொரு பகுதியாக நடத்தலாம்.',
  'brief.useTurn': 'ஒவ்வொரு பகுதியாக', // 16 Oct handover (F1-F3): the mode's own name, so it is one line at 320 px (the old verb phrase was two lines at 375). DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.submitFailed': 'பதில்கள் பதிவாயின, ஆனால் இன்னும் சரிபார்க்க முடியவில்லை',
  'brief.notRecordedHint': 'ஒவ்வொரு பகுதியாக முறை ஸ்கிரிப்டை மீண்டும் வாசித்து, சர்வர் சரிபார்க்கக்கூடிய வகையில் பதில்களைப் பதிவு செய்யும்.',
  'brief.err.connect_failed': 'நேரடிக் குரல் இணைப்பைத் திறக்க முடியவில்லை.',
  'brief.err.socket_closed': 'நேரடிக் குரல் இணைப்பு துண்டிக்கப்பட்டது.',
  'brief.err.timeout': 'நேரடிக் குரல் சேவை பதிலளிக்கவில்லை.',
  'brief.err.protocol': 'நேரடிக் குரல் சேவை எதிர்பாராத ஒன்றை அனுப்பியது.',
  'brief.err.bad_ticket': 'நேரடிக் குரல் இணைப்பு ஏற்கப்படவில்லை. மீண்டும் முயலுங்கள்.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.err.bad_message': 'நேரடிக் குரல் சேவை ஒரு செய்தியை நிராகரித்தது.',
  'brief.err.invalid_state': 'இந்தச் சுற்றில் இப்போது குரல் அமர்வைத் தொடங்க முடியாது.',
  'brief.err.limit': 'இந்தச் சுற்றுக்கான நேரடிக் குரல் வரம்பு எட்டப்பட்டது.',
  'brief.err.upstream_busy': 'குரல் சேவை பிஸியாக உள்ளது. சிறிது நேரம் கழித்து முயலுங்கள்.',
  'brief.err.tts_failed': 'பதிவு செய்யப்பட்ட குரலைத் தயாரிக்க முடியவில்லை.',
  'brief.err.aborted': 'சுற்று முடிக்கப்பட்டது.',
  'brief.err.unknown': 'குரல் அமர்வு தோல்வியடைந்தது.',
  'brief.err.submit': 'சர்வரால் பதில்களைச் சரிபார்க்க முடியவில்லை. மீண்டும் முயலுங்கள்; பதிவுகள் இந்தச் சாதனத்தில் உள்ளன.',
  'brief.sample.label': 'இந்தச் சுற்றுக்குச் சேமித்த மாதிரிப் பதில்களைப் பயன்படுத்து', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.checking': 'சேமித்த மாதிரிப் பதிலைத் தேடுகிறது…', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.all': 'எல்லாக் கேள்விகளுக்கும் சேமித்த மாதிரிப் பதில் உள்ளது. யாரும் {lang} பேசத் தேவையில்லை.', // 16 Oct, every question has a sample (build-notes/30): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.has': 'கேள்வி {list}-க்குச் சேமித்த மாதிரிப் பதில் உள்ளது.', // 16 Oct (build-notes/30): the first sentence of the earlier line. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.hasMany': 'கேள்விகள் {list}-க்குச் சேமித்த மாதிரிப் பதில்கள் உள்ளன.', // 16 Oct (build-notes/30): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.synthetic': 'அது செயற்கைக் குரல், தொழிலாளர் அல்ல; முடிவில் அது மாதிரி என்று குறிக்கப்படும்.', // 16 Oct (build-notes/30): the second sentence of the earlier line. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.syntheticMany': 'அவை செயற்கைக் குரல், தொழிலாளர் அல்ல; முடிவில் அவை மாதிரி என்று குறிக்கப்படும்.', // 16 Oct (build-notes/30): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.rest': 'மற்ற கேள்விகளுக்குத் தொழிலாளர் குரலில் பதில் சொல்வார்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.stepsLeft': 'சில படிகள் எந்தச் சேமித்த பதிலிலும் இல்லை, அதனால் அவற்றுக்கு இன்னொரு சுற்று தேவைப்படலாம்.', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.none': 'இந்தப் பணி, மொழி, சுற்றுக்குச் சேமித்த மாதிரிப் பதில் இல்லை. எல்லாக் கேள்விகளுக்கும் தொழிலாளர் குரலில் பதில் சொல்வார்.', // 16 Oct handover (F1-F3): DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.failed': 'மாதிரிப் பதிலை இயக்க முடியவில்லை; தொழிலாளர் குரலில் பதில் சொன்னார்.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.sample.dropped': 'மாதிரிப் பதில் அந்தக் கேள்விக்குத் தாமதமாக வந்ததால் பயன்படுத்தப்படவில்லை.',
  'brief.reportHeld': 'தொழிலாளரின் பிரச்சனைப் பதிவு அனுப்பப்படவில்லை',
  'brief.reportHeldHint': 'இந்தத் திரையில் உள்ள தொழிலாளரின் பொத்தான்களால் அதை மீண்டும் அனுப்புங்கள் அல்லது நீக்குங்கள். அதன் பிறகு முடிவு திறக்கும்.', // 16 Oct handover (F1-F3): reworded. DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'brief.reportHoldsPage': 'ஒரு பிரச்சனைப் பதிவு இன்னும் அனுப்பப்படவில்லை. முதலில் அனுப்புங்கள் அல்லது நீக்குங்கள்.',

  'result.title': 'சுற்று {n} சரிபார்ப்பு',
  'result.subtitle': 'ஒவ்வொரு படியிலும் தொழிலாளர் திருப்பிச் சொன்னது காட்டப்படுகிறது. சரிபார்ப்பு பதிலைப் பற்றியது; நபரைப் பற்றியது அல்ல.',
  'result.announce': 'சுற்று {n} சரிபார்க்கப்பட்டது. இன்னும் திறந்துள்ள படிகள்: {open}.',
  'result.glance': 'ஒரே பார்வையில்',
  'result.steps': 'முக்கியப் படிகள்',
  'result.stepN': 'படி {n}',
  'result.hazard': 'ஆபத்து: {hazard}',
  'result.workerSaid': 'தொழிலாளர் சொன்னது ({lang})',
  'result.sampleSaid': 'சேமித்த மாதிரிப் பதில் சொன்னது ({lang})', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'result.inLang': '{lang} மொழியில்',
  'result.why': 'காரணம்:',
  'result.noMention': 'பதிலில் இந்தப் படி குறிப்பிடப்படவில்லை.',
  'result.notClear': 'கணக்கில் கொள்ளும் அளவு தெளிவில்லை. மீண்டும் கேளுங்கள்.',
  'result.noQuote': 'இந்தப் படிக்கு மேற்கோள் பதிவாகவில்லை.',
  'result.earlier': 'முந்தைய சுற்றில் சொல்லப்பட்டவை',
  'result.answers': 'தொழிலாளர் சொன்னது',
  'result.answersHint': '{lang} மொழியில், பதிவான படி, மொழிபெயர்ப்புடன்.',
  'result.question': 'கேள்வி {n}',
  'result.play': 'பதில் {n}-ஐ இயக்கு',
  'result.stop': 'நிறுத்து',
  'result.noSpeech': 'பேச்சு எதுவும் கேட்கவில்லை.',
  'result.modelRefused': 'சரிபார்ப்பியால் இந்தப் பதிலைச் செயலாக்க முடியவில்லை. மீண்டும் கேளுங்கள் அல்லது நேரில் சரிபாருங்கள்.', // v0.5.1: DRAFT
  'result.noTranscript': 'இந்தக் கேள்விக்கு எழுத்துப் பதிவு இல்லை.',
  'result.detected': 'கேட்டது: {lang}',
  'result.otherLang': 'வேறு மொழி',
  'result.exhausted': 'சில படிகள் இன்னும் திறந்துள்ளன',
  'result.exhaustedHint': '{max} சுற்றுகளுக்குப் பிறகு, இந்தப் படிகளைச் செய்து காட்டச் சொல்லிச் சரிபாருங்கள்.',
  'result.sample': 'மாதிரிப் பதில் (செயற்கைக் குரல்)',
  'result.deliveryWhy': '"மீண்டும் கேளுங்கள்" ஏன்: குரல் ஸ்கிரிப்டை விட்டு விலகியது',
  'result.deliveryWhyGeneric': 'இந்தப் படிக்கு நீங்கள் உறுதிசெய்த ஸ்கிரிப்டைக் குரல் சொல்லவில்லை.',
  'result.deliveryWhyHint': 'தொழிலாளர் உங்கள் ஸ்கிரிப்டிலிருந்து வேறுபட்ட ஒன்றைக் கேட்டிருக்கலாம்; எனவே மீண்டும் கேட்ட பிறகே இந்தப் படி கணக்கில் கொள்ளப்படும். இதை மீண்டும் விளக்குங்கள்.', // v0.5.3: DRAFT
  'result.deliveryWhyEarlier': 'இது இந்தப் படிக்கான கேள்விக்கு முன் நடந்தது; எனவே தொழிலாளர் ஏற்கெனவே ஒரு குறிப்பைக் கேட்டிருக்கலாம்.',
  // v0.5.3 (F4): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. What to do when the two judges split.
  'result.disagreedAsk': 'இரண்டு சரிபார்ப்புகளும் மாறுபட்டன; எனவே இந்தப் படி "மீண்டும் கேளுங்கள்" என வருகிறது. பதிலைக் கேளுங்கள்; பிறகு இந்தப் படியை மீண்டும் விளக்குங்கள் அல்லது நேரில் சரிபாருங்கள்.',
  'result.disagreedWrong': 'இரண்டு சரிபார்ப்புகளும் மாறுபட்டன; ஒன்று இந்தப் படிக்கு நேர் எதிரானதைக் கண்டது; எனவே இது "தவறு" என வருகிறது. தீர்மானிக்கும் முன் பதிலைக் கேளுங்கள்.',
  // v0.5: shortened so each fits one line on a 320 px phone (the result screen's buttons). DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'result.reexplain': 'மீதிப் படிகளை விளக்கு',
  'result.decide': 'தீர்மானி: Go / No-go',
  'delivery.title': 'குரல் உங்கள் ஸ்கிரிப்டைப் பின்பற்றவில்லை',
  'delivery.hint': 'குரல் சொன்னதை உறுதிசெய்த ஸ்கிரிப்டுடன் குறியீடு ஒப்பிடுகிறது. கீழே உள்ள பகுதி சொல்லும் அல்லது கேட்கும் படிகள், பதில் சரியாக இருந்தாலும், "மீண்டும் கேளுங்கள்" ஆகும்.',
  'delivery.said': 'குரல் சொன்னது ({lang})',
  'delivery.script': 'நீங்கள் உறுதிசெய்த ஸ்கிரிப்ட்',
  'delivery.instruction': 'அறிவுறுத்தல்',
  'delivery.closing': 'நிறைவு வரி',
  'delivery.question': 'கேள்வி {n}',
  'delivery.not_spoken': 'குரல் {what}-ஐச் சொல்லவில்லை.',
  'delivery.wrong_script': 'குரல் {what}-ஐ வேறு மொழியில் சொன்னது.',
  'delivery.low_similarity': 'குரல் {what}-ஐ உங்கள் ஸ்கிரிப்டிலிருந்து வேறு சொற்களில் சொன்னது.',
  'delivery.number_changed': '{what}-இல் ஒரு எண் மாறியது.',
  'delivery.negation_dropped': 'குரல் {what}-இல் ஒரு மறுப்பை ("இல்லை", "வேண்டாம்") விட்டுவிட்டது.',
  'delivery.negation_added': 'குரல் {what}-இல் ஒரு மறுப்பை ("இல்லை", "வேண்டாம்") சேர்த்துவிட்டது.',
  'delivery.negation_changed': '{what}-இல் ஒரு மறுப்பு ("இல்லை", "வேண்டாம்") மாறியது.',
  'delivery.reply_too_long': 'கேள்வி {n}-க்குப் பிறகு குரல் ஒரு நன்றியை விட அதிகம் சொன்னது.',
  'delivery.reply_not_neutral': 'கேள்வி {n}-க்குப் பிறகு குரல் வெறும் நன்றி மட்டுமல்லாமல் ஸ்கிரிப்டிலிருந்து சொற்களைச் சொன்னது.',
  'delivery.mismatch': '{what}-க்குக் குரல் சொன்னது உங்கள் ஸ்கிரிப்டுடன் பொருந்தவில்லை.',
  'models.title': 'இந்தப் பதில்களைச் சரிபார்த்தவை',
  'models.unknown': 'பதிவாகவில்லை',
  'models.transcribe': 'படிகளை அறியாத எழுத்தாக்கி',
  'models.transcribeHint': 'படிகளைப் பார்க்காமல் தொழிலாளர் சொன்னதை எழுதுகிறது.',
  'models.judgeA': 'மதிப்பீட்டாளர் A',
  'models.judgeAHint': 'ஒலியைக் கேட்டு, எழுத்துப் பதிவையும் படிக்கிறது.',
  'models.judgeB': 'மதிப்பீட்டாளர் B',
  'models.judgeBHint': 'எழுத்துப் பதிவை மட்டும் படிக்கிறது; மதிப்பீட்டாளர் A-விலிருந்து வேறு மாடலில்.',
  'models.judgeBSame': 'எழுத்துப் பதிவை மட்டும் படிக்கிறது; மதிப்பீட்டாளர் A-வின் அதே மாடலில்.',
  'models.guard': 'காவல் விதிகள்',
  'models.guardValue': 'குறியீடு, மாடல் இல்லை',
  // v0.5.3 (F7): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. The old text said "the worse verdict wins"; that rule ended in v0.5.3.
  'models.guardHint': 'இறுதி முடிவை எடுக்கிறது. இரண்டு மதிப்பீட்டாளர்களும் ஒத்துப்போனால் அதுவே நிற்கும். ஒருவர் முரண்பாட்டைக் கண்டாலும் அதுவே நிற்கும். வேறு எந்த மாறுபாடும் "மீண்டும் கேளுங்கள்" ஆகும், ஒருபோதும் "சொல்லப்பட்டது" அல்ல. மேற்கோள் எழுத்துப் பதிவில் உண்மையிலேயே இருக்க வேண்டும்.',
  'hazard.title': 'தொழிலாளர் சொன்ன பிரச்சனைகள் ({n})',
  'hazard.hint': 'ஒவ்வொன்றுக்கும் நீங்கள் என்ன செய்தீர்கள் என்ற குறிப்பு வரும் வரை Go பூட்டப்பட்டிருக்கும்.',
  'hazard.card': 'பிரச்சனை {n}',
  'hazard.open': 'இன்னும் கவனிக்கப்படவில்லை',
  'hazard.acked': 'கவனிக்கப்பட்டது',
  'hazard.during': 'சுற்று {n}-இல் சொல்லப்பட்டது, {time}',
  'hazard.tap': 'தொழிலாளர் எதுவும் சொல்லாமல் "பிரச்சனை உள்ளது" பொத்தானை அழுத்தினார். என்ன பிரச்சனை என்று அவரிடம் கேளுங்கள்.',
  'hazard.said': 'தொழிலாளர் சொன்னது ({lang})',
  'hazard.noWords': 'பதிவில் சொற்கள் எதுவும் இல்லை. என்ன பிரச்சனை என்று தொழிலாளரிடம் கேளுங்கள்.',
  'hazard.ackedBy': 'செய்தது: {by} குறித்தது, {time}',
  'hazard.ackedAt': 'செய்தது: குறித்த நேரம் {time}',
  'hazard.noteLabel': 'இதற்கு நீங்கள் என்ன செய்தீர்கள்?',
  'hazard.noteHint': 'குறைந்தது {min} எழுத்துகள். பிரீஃபிங்குடன் பதிவாகும்.',
  'hazard.noteShort': 'குறைந்தது {min} எழுத்துகள் எழுதுங்கள்.',
  'hazard.ack': 'செய்ததைப் பதிவு செய்',
  'hazard.ackDone': 'பிரச்சனை {n}-க்கான உங்கள் குறிப்பு பதிவானது.',
  'hazard.announce': 'தொழிலாளர் சொன்ன பிரச்சனைகள்: {n}.',
  // v0.5.3 (F4): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. The compact banner that jumps to the note.
  'hazard.banner': 'தொழிலாளர் ஒரு பிரச்சனையைச் சொன்னார் · நீங்கள் செய்ததைக் குறிக்கும் வரை Go பூட்டப்பட்டுள்ளது',
  'hazard.bannerMany': 'தொழிலாளர் {n} பிரச்சனைகளைச் சொன்னார் · நீங்கள் செய்ததைக் குறிக்கும் வரை Go பூட்டப்பட்டுள்ளது',
  'hazard.bannerAction': 'குறிப்பு எழுது', // one line at 320 px

  'reexplain.title': 'திறந்த படிகளை மீண்டும் விளக்குங்கள்',
  // v0.5.3 (F6): the subtitle is now the first sentence only, so both choices fit above the bar; the second moved to the open steps. DRAFT.
  'reexplain.subtitle': 'தொழிலாளர் அதை மீண்டும் எப்படிக் கேட்க வேண்டும் எனத் தேர்ந்தெடுங்கள்.',
  'reexplain.openHint': 'பிறகு இந்தப் படிகளைப் பற்றி மட்டும் புதிய கேள்விகள் கேட்கப்படும்.',
  'reexplain.kind': 'திரும்பி வராத படியை, அதே சொற்களை உரக்கச் சொல்லாமல், வேறு விதமாக விளக்குங்கள். முடிந்தால், உண்மையான பொருளைக் காட்டி விளக்குங்கள்.', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'reexplain.open': 'திறந்த படிகள் ({n})',
  'reexplain.how': 'எப்படி விளக்க வேண்டும்?',
  'reexplain.generate': 'கவனம் செலுத்திய மீள் விளக்கம்',
  'reexplain.generateHint': 'சுருக்கமாக, எளிய {lang}. தொழிலாளர் கேட்கும் முன் நீங்கள் பார்க்கலாம்.', // v0.5.3 (F6): shortened so both choices fit above the bar. DRAFT
  'reexplain.own': 'என் சொந்தச் சொற்கள்',
  'reexplain.ownHint': 'உங்கள் மொழியில் தட்டச்சு செய்யுங்கள். {lang} மொழியில் மொழிபெயர்க்கப்படும்.', // v0.5.3 (F6): shortened. DRAFT
  'reexplain.ownLabel': 'உங்கள் மீள் விளக்கம்',
  'reexplain.write': 'மீள் விளக்கத்தை எழுது', // v0.5.3 (F6): DRAFT, NEEDS NATIVE-SPEAKER REVIEW
  'reexplain.busy': '{lang} மீள் விளக்கத்தையும் புதிய கேள்விகளையும் எழுதுகிறது…',
  'reexplain.need': 'முதலில் உங்கள் மீள் விளக்கத்தைத் தட்டச்சு செய்யுங்கள்', // v0.5.3 (F6): DRAFT, NEEDS NATIVE-SPEAKER REVIEW

  'decision.title': 'உங்கள் தீர்மானம்',
  'decision.subtitle': 'தொழிலாளர் திருப்பிச் சொன்னதை இந்தக் கருவி சரிபார்த்தது. வேலை தொடங்குமா என்பதை நீங்களே தீர்மானிக்கிறீர்கள்.',
  'decision.checked': 'சரிபார்க்கப்பட்டவை',
  'decision.rounds': 'நடத்திய சுற்றுகள்: {n}',
  'decision.openTitle': 'இன்னும் திறந்துள்ள படிகள்: {n}',
  'decision.openHint': 'அப்படியும் வேலை தொடங்கினால் ஏன் என்று எழுதுங்கள். காரணம் உங்கள் தீர்மானத்துடன் பதிவாகும்.',
  'decision.choose': 'Go அல்லது No-go',
  'decision.go': 'Go',
  'decision.goHint': 'வேலை தொடங்கலாம்.',
  'decision.goLocked': 'ஒவ்வொரு பிரச்சனைக்கும் குறிப்பு வரும் வரை பூட்டப்பட்டுள்ளது.', // v0.5.3 (follow-up): shortened so both choices fit above the bar. DRAFT
  'decision.sampleOpen': 'சேமித்த மாதிரிப் பதிலால் மட்டும் சொல்லப்பட்ட படிகள் திறந்தவையாகக் கருதப்படும்: தொழிலாளர் அவற்றைச் சொல்லவில்லை.',
  'decision.noGo': 'No-go',
  'decision.noGoHint': 'வேலை இன்னும் தொடங்காது.',
  'decision.reason': 'காரணம் (விருப்பம்)',
  'decision.reasonRequired': 'காரணம் (அவசியம்)',
  'decision.reasonHint': 'குறைந்தது {min} எழுத்துகள். திறந்த படிகளுடன் வேலை ஏன் தொடங்கலாம் என்று சொல்லுங்கள்.',
  'decision.reasonHintSample': 'குறைந்தது {min} எழுத்துகள். சேமித்த மாதிரிப் பதில் சொன்ன படிகள் திறந்தே இருக்கும், ஏனெனில் தொழிலாளர் அவற்றைச் சொல்லவில்லை. வேலை ஏன் தொடங்கலாம் என்று சொல்லுங்கள்.', // 16 Oct: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'decision.reasonShort': 'குறைந்தது {min} எழுத்துகள் எழுதுங்கள்.',
  'decision.by': 'உங்கள் பெயர் அல்லது முதலெழுத்துகள் (விருப்பம்)',
  'decision.byHint': 'தீர்மானத்துடன் பதிவாகும். ஒருபோதும் தொழிலாளர் பெயர் அல்ல.',
  'decision.record': 'தீர்மானத்தைப் பதி', // v0.5: shortened (one line at 320 px). DRAFT
  // v0.5.3 (F5): DRAFT, NEEDS NATIVE-SPEAKER REVIEW. Why Record decision is off, and the confirm before it.
  'decision.need.choice': 'Go அல்லது No-go-ஐத் தேர்ந்தெடுங்கள்',
  'decision.need.reason': 'திறந்த படிகளுடன் வேலை ஏன் தொடங்கலாம் என்று எழுதுங்கள்',
  'decision.need.hazard': 'சொல்லப்பட்ட பிரச்சனைக்கு நீங்கள் செய்ததைக் குறியுங்கள்',
  'decision.backToResult': 'முடிவுக்குத் திரும்பு',
  'decision.confirm.title': '{value} என்று பதியவா?',
  'decision.confirm.body': 'இது இறுதியானது. பதிவைத் திருத்த முடியாது.',
  'decision.confirm.open': 'இன்னும் திறந்துள்ள படிகள்: {n}. உங்கள் காரணம் தீர்மானத்துடன் பதிவாகும்.',
  'decision.confirm.noGoKind': 'No-go என்பது தொழிலாளர் மீதான குறை அல்ல. பதிவிலிருந்து அவருக்கு மீண்டும் விளக்கலாம்.', // 16 Oct compassion pass: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'decision.confirm.cancel': 'தொடர்ந்து திருத்து',
  'decision.confirm.go': 'Go எனப் பதி',
  'decision.confirm.noGo': 'No-go எனப் பதி',

  'record.title': 'பிரீஃபிங் பதிவு',
  'record.subtitle': 'என்ன சரிபார்க்கப்பட்டது, நீங்கள் என்ன தீர்மானித்தீர்கள்.',
  'record.new': 'புதிய பிரீஃபிங்', // v0.5: shortened (one line at 320 px). DRAFT
  'record.all': 'அனைத்துப் பதிவுகள்',
  'record.by': 'தீர்மானித்தவர்: {by}',
  'record.reason': 'காரணம்',
  'record.openAtDecision': 'தீர்மானத்தின்போது திறந்திருந்த படிகள்: {n}',
  'record.checked': 'சரிபார்க்கப்பட்டவை',
  'record.open': 'தீர்மானத்தில் திறந்திருந்தது',
  'record.rounds': 'சுற்றுகள்',
  'record.roundN': 'சுற்று {n}',
  'record.initial': 'முதல் பிரீஃபிங்',
  'record.reexplain': 'மீள் விளக்கம்',
  'record.meta': 'பிரீஃபிங்:',
  'record.note': 'இந்தப் பதிவு என்ன சரிபார்க்கப்பட்டது, நீங்கள் என்ன தீர்மானித்தீர்கள் என்பதை மட்டும் காட்டுகிறது. தொழிலாளருக்கு மதிப்பெண் இல்லை; தொழிலாளர் பெயர், அடையாள எண் அல்லது ஒலிப்பதிவு சேமிக்கப்படாது.',
  // v0.5.2: DRAFT, NEEDS NATIVE-SPEAKER REVIEW.
  'record.permit': 'வேலை அனுமதி',
  'record.nextWorker': 'அடுத்தவர் ({n}/{m})', // "the next one", as the card above says; one line at 320 px
  'record.nextWorkerHint': 'இந்த அனுமதியில் அடுத்தவர்: தொழிலாளர் {n} / {m}. அதே தளம், பணி, மொழிகள், அனுமதி; அறிவுறுத்தல் நிரப்பப்பட்டுள்ளது, மாற்றலாம்.',
  'record.permitLast': 'தொழிலாளர் {m} / {m}, இந்த அனுமதியில் கடைசி. அனுமதியை விடுவிப்பதா என்பதை அனுமதி அமைப்பு தீர்மானிக்கும்: ஒவ்வொரு தொழிலாளருக்கும் Go வேண்டும்.',
  'record.mockBoard': 'மாதிரி அனுமதிப் பலகை: {crew} பேரில் {verified} பேருக்கு Go · {status}',
  'record.hazardsAtDecision': 'தீர்மானத்தின்போது திறந்திருந்த பிரச்சனைகள்: {n}',
  // v0.5.3: DRAFT, NEEDS NATIVE-SPEAKER REVIEW. After a No-go on a permit: the same worker again on the same permit.
  'record.decisionTitle': 'தீர்மானம்',
  'record.rebrief': 'தொழிலாளர் {n}-ஐ மீண்டும்', // one line at 320 px
  'record.rebriefHint': 'தொழிலாளர் {n} / {m}-க்கு No-go. அனுமதியில் உள்ள ஒவ்வொருவருக்கும் Go இருந்தால் மட்டுமே அனுமதி விடுவிக்கப்படும்; ஒவ்வொரு தொழிலாளருக்கும் கடைசித் தீர்மானத்தையே அனுமதி அமைப்பு வைத்திருக்கும். இதே அனுமதியில் இந்தத் தொழிலாளருக்கு மீண்டும் பிரீஃபிங் செய்யலாம்.',
  'chain.title': 'மாற்றச் சரிபார்ப்பு',
  'chain.how': 'இந்தப் பிரீஃபிங்கின் ஒவ்வொரு மாற்றமும் படிகள், ஸ்கிரிப்டுகள், மதிப்பீடுகள், தீர்மானம் ஆகியவற்றைப் பிணைக்கும் SHA-256 சங்கிலியின் ஒரு கண்ணி. சர்வர் முழுச் சங்கிலியையும் மீண்டும் கணக்கிடுகிறது.',
  'chain.checking': 'பதிவின் சங்கிலியைச் சரிபார்க்கிறது…',
  'chain.failed': 'இப்போது சங்கிலியைச் சரிபார்க்க முடியவில்லை.',
  'chain.ok': 'பதிவு சரிபார்க்கப்பட்டது · {n} நிகழ்வுகள் · சங்கிலி முழுமையாக உள்ளது',
  'chain.head': 'சங்கிலித் தலை',
  'chain.broken': 'இந்தப் பதிவு அதன் சங்கிலியுடன் பொருந்தவில்லை',
  'chain.brokenAt': 'நிகழ்வு {seq}-இல் ({type}) சரிபார்ப்பு தோல்வியடைகிறது.',
  'chain.refused': 'தீர்மானத்துக்குப் பிறகு திருத்தங்கள் மறுக்கப்படும்.',
  'chain.samples': 'சேமித்த மாதிரிப் பதில்கள்',
  'chain.noSamples': 'இந்தப் பிரீஃபிங்கில் சேமித்த மாதிரிப் பதில் எதுவும் பயன்படுத்தப்படவில்லை.',
  'chain.sampleLine': 'சுற்று {round}, கேள்வி {q}: சேமித்த செயற்கைக் குரல், தொழிலாளர் அல்ல',
  'chain.timeline': 'நிகழ்வுகள் ({n})',
  'chain.none': 'மாற்றச் சரிபார்ப்பு வருவதற்கு முன் இந்தப் பதிவு உருவானது; சரிபார்க்க அதற்குச் சங்கிலி இல்லை.',
  'chain.reason.seq_mismatch': 'ஒரு நிகழ்வு இல்லை, அல்லது வரிசை மாறியுள்ளது.',
  'chain.reason.prev_hash_mismatch': 'ஒரு நிகழ்வு அதற்கு முந்தையதுடன் இணையவில்லை.',
  'chain.reason.hash_mismatch': 'ஒரு நிகழ்வின் ஹாஷ் பதிவான மதிப்புடன் பொருந்தவில்லை.',
  'chain.reason.instruction_mismatch': 'அறிவுறுத்தல் பதிவானதிலிருந்து மாறியுள்ளது.',
  'chain.reason.sop_mismatch': 'SOP பதிவானதிலிருந்து மாறியுள்ளது.',
  'chain.reason.steps_mismatch': 'படிகள் பதிவானவற்றிலிருந்து மாறியுள்ளன.',
  'chain.reason.script_mismatch': 'ஒரு சுற்றின் ஸ்கிரிப்ட் பதிவானதிலிருந்து மாறியுள்ளது.',
  'chain.reason.ratings_mismatch': 'ஒரு சுற்றின் மதிப்பீடுகள் பதிவானவற்றிலிருந்து மாறியுள்ளன.',
  'chain.reason.round_missing': 'பதிவான ஒரு சுற்று காணவில்லை.',
  'chain.reason.hazard_mismatch': 'சொல்லப்பட்ட ஒரு பிரச்சனை பதிவானதிலிருந்து மாறியுள்ளது.',
  'chain.reason.hazard_missing': 'சொல்லப்பட்ட ஒரு பிரச்சனை காணவில்லை.',
  'chain.reason.decision_mismatch': 'தீர்மானம் பதிவானதிலிருந்து மாறியுள்ளது.',
  'chain.reason.record_hash_mismatch': 'பதிவின் ஹாஷ் அதன் கடைசி நிகழ்வின் ஹாஷ் அல்ல.',
  'chain.reason.unrecorded_change': 'எந்த நிகழ்விலும் பதிவாகாத ஒரு மாற்றம் பதிவில் உள்ளது.',
  'chain.reason.other': 'எழுதிய பிறகு பதிவு மாறியுள்ளது.',
  'event.created': 'பிரீஃபிங் உருவாக்கப்பட்டது',
  'event.instruction_edited': 'அறிவுறுத்தல் திருத்தப்பட்டது',
  'event.steps_proposed': 'முக்கியப் படிகள் பட்டியலிடப்பட்டன',
  'event.steps_confirmed': 'படிகள் உறுதிசெய்யப்பட்டன',
  'event.round_created': 'சுற்று {n}-க்கு ஸ்கிரிப்ட் எழுதப்பட்டது',
  'event.script_approved': 'சுற்று {n}-இன் ஸ்கிரிப்ட் உறுதிசெய்யப்பட்டது',
  'event.round_judged': 'சுற்று {n}-இல் பதில்கள் சரிபார்க்கப்பட்டன',
  'event.hazard_raised': 'பிரச்சனை {n} சொல்லப்பட்டது',
  'event.hazard_acknowledged': 'பிரச்சனை {n} கவனிக்கப்பட்டது',
  'event.decided': 'தீர்மானம் பதிவானது',
}
