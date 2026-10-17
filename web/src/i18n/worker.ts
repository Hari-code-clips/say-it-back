// The few static words on the worker's screen, in each worker language. Everything else the
// worker reads or hears (instruction, questions, captions, closing) comes from the backend.
//
// DRAFT: these translations are machine-written and NEED NATIVE-SPEAKER REVIEW before any real
// use (Tamil, Bengali, Burmese, Hindi, Odia and Telugu in particular). English and Chinese are the
// least risky; the rest are marked for review in the catalog note as well.
import type { Lang } from '../api/types.ts'

export interface WorkerWords {
  /** Big start button on the hand-over screen. */
  start: string
  /** Compassion pass (16 Oct): what happens next, above Start. Teach-back asks for the worker's own words, not the script's. */
  readyHow: string
  /** Under it: the worker is never scored (product rule 3), and "it is not clear" is an answer the check wants to hear. */
  readyKind: string
  /** The hand-back screen opens with a thank-you before it asks for the phone. */
  thanks: string
  /** The phone is speaking: the worker listens. */
  listen: string
  /** The worker's turn. */
  speak: string
  /** Ends the answer. */
  done: string
  /** Between steps / while the answer is being checked. */
  wait: string
  /** v0.4, the worker's problem report (endpoint 21). The button, on every worker screen outside an answer window. */
  report: string
  /** The report sheet's title. */
  reportTitle: string
  /** Record the problem by voice. */
  reportSpeak: string
  /** The recording's limit, shown beside the button (a label must never wrap). */
  reportLimit: string
  /** Send the report with no words (a tap). */
  reportTap: string
  /** While recording. */
  reportRecording: string
  reportSend: string
  reportCancel: string
  reportSending: string
  /** The confirmation. */
  reportSent: string
  reportFailed: string
  /** The microphone could not start: a tap still works. */
  reportNoMic: string
  /** The closing screen: the phone goes back to the supervisor. */
  handBack: string
  /** F2: any failure while the worker holds the phone. The details are for the supervisor and wait behind a held button. */
  giveSupervisor: string
  /** v0.4 review: a failed report is kept until it is sent again or deleted on purpose, with a confirm. */
  reportDiscard: string
  reportDiscardTitle: string
  reportDiscardBody: string
  reportDiscardConfirm: string
  reportKeep: string
  /** Privacy (16 Oct): one calm screen before the first answer is recorded, one decision (ConsentStep.tsx). */
  consentWhat: string
  /** What the voice is for and that it is deleted: the phone keeps it only until its check answers (24 hours at most), the service
   *  drops it after judging unless SIB_KEEP_AUDIO. */
  consentUse: string
  /** The primary choice. */
  consentAgree: string
  /** The other choice: it ends the round kindly; the supervisor briefs in person. Never a failure. */
  consentNotNow: string
}

// v0.4 problem-report words: DRAFT in every language but English, NEED NATIVE-SPEAKER REVIEW.
// 16 Oct handover word `giveSupervisor` (a failure on the worker's screen): DRAFT in every language but English, NEED NATIVE-SPEAKER REVIEW.
// 16 Oct compassion pass, `readyHow`, `readyKind`, `thanks` and the thank-you added to `reportSent`: DRAFT in every language but
// English, NEED NATIVE-SPEAKER REVIEW (Tamil first: build-notes/32-compassion-pass.md).
// It uses the everyday spoken words of its sibling `handBack` (phone, supervisor), never a spelled-out technical term.
// 16 Oct privacy pass, `consentWhat`, `consentUse`, `consentAgree`, `consentNotNow`: DRAFT in every language but English, NEED
// NATIVE-SPEAKER REVIEW (Tamil first: build-notes/34-privacy.md). Tamil avoids ஒப்புதல் (approval, banned by rule 2): சம்மதம் is agreeing.
// 17 Oct (build-notes/37-telugu-consent.md): every Telugu word (`te`, a worker language of the Chennai site), and the disclosure added
// to `consentUse` in every language (outside review P0-14: the voice goes to Google's computers outside the worker's country, only to
// check this briefing, and is deleted after the check, within a day): DRAFT in every language but English, NEED NATIVE-SPEAKER REVIEW.
// "Computers" is the everyday word for Google's cloud servers; "outside this country" fits a worker in Singapore and one in Chennai.
export const WORKER_WORDS: Record<Lang, WorkerWords> = {
  en: {
    start: 'Start', listen: 'Listen', speak: 'Speak now', done: 'Done', wait: 'Please wait',
    readyHow: 'Listen. Then say it back in your own words.', readyKind: 'This is not a test of you. If something is not clear, say so.', thanks: 'Thank you',
    report: 'Report a problem', reportTitle: 'What is wrong?', reportSpeak: 'Say it', reportLimit: 'Up to 30 seconds', reportTap: 'Send without words',
    reportRecording: 'Recording. Say what is wrong.', reportSend: 'Send', reportCancel: 'Cancel', reportSending: 'Sending…',
    reportSent: 'Thank you for speaking up. Your supervisor will see this.', reportFailed: 'Not sent. Try again.', reportNoMic: 'The microphone is not working. You can still send without words.',
    handBack: 'Please give the phone back to your supervisor',
    giveSupervisor: 'Please give the phone to your supervisor',
    reportDiscard: 'Delete report', reportDiscardTitle: 'Delete this report?', reportDiscardBody: 'Your supervisor will not see it.', reportDiscardConfirm: 'Delete', reportKeep: 'Keep it',
    consentWhat: 'We will record your answers.', consentUse: "Your voice goes to Google's computers outside this country, only to check this briefing. It is deleted after the check, within a day.", consentAgree: 'I agree', consentNotNow: 'Not now',
  },
  zh: {
    start: '开始', listen: '请听', speak: '请回答', done: '说完了', wait: '请稍等',
    readyHow: '先听，然后用你自己的话说一遍。', readyKind: '这不是考你。哪里不清楚，就直接说。', thanks: '谢谢',
    report: '报告问题', reportTitle: '哪里有问题？', reportSpeak: '说出来', reportLimit: '最多 30 秒', reportTap: '不说话，直接发送',
    reportRecording: '正在录音，请说出问题。', reportSend: '发送', reportCancel: '取消', reportSending: '正在发送…',
    reportSent: '谢谢你说出来。你的主管会看到。', reportFailed: '没有发出去，请再试一次。', reportNoMic: '麦克风不能用。你仍然可以不说话直接发送。',
    handBack: '请把手机交还给你的主管',
    giveSupervisor: '请把手机交给你的主管',
    reportDiscard: '删除报告', reportDiscardTitle: '删除这条报告？', reportDiscardBody: '你的主管将看不到它。', reportDiscardConfirm: '删除', reportKeep: '保留',
    consentWhat: '我们会录下你的回答。', consentUse: '你的声音会传到谷歌在这个国家以外的电脑上，只用来核对这次的说明。核对后删除，最多保留一天。', consentAgree: '我同意', consentNotNow: '现在不要',
  },
  ta: {
    start: 'தொடங்கு', listen: 'கேளுங்கள்', speak: 'இப்போது பேசுங்கள்', done: 'முடிந்தது', wait: 'காத்திருங்கள்',
    readyHow: 'கேளுங்கள். பிறகு உங்கள் சொந்த வார்த்தைகளில் திருப்பிச் சொல்லுங்கள்.', readyKind: 'இது உங்களுக்கான தேர்வு இல்லை. ஏதாவது தெளிவாக இல்லை என்றால், சொல்லுங்கள்.', thanks: 'நன்றி',
    report: 'பிரச்சனை உள்ளது', reportTitle: 'என்ன பிரச்சனை?', reportSpeak: 'பேசிச் சொல்லுங்கள்', reportLimit: '30 வினாடி வரை', reportTap: 'பேசாமல் அனுப்பு',
    reportRecording: 'பதிவாகிறது. என்ன பிரச்சனை என்று சொல்லுங்கள்.', reportSend: 'அனுப்பு', reportCancel: 'வேண்டாம்', reportSending: 'அனுப்புகிறது…',
    reportSent: 'சொன்னதற்கு நன்றி. உங்கள் சூப்பர்வைசர் இதைப் பார்ப்பார்.', reportFailed: 'அனுப்ப முடியவில்லை. மீண்டும் முயலுங்கள்.', reportNoMic: 'மைக் வேலை செய்யவில்லை. பேசாமலும் அனுப்பலாம்.',
    handBack: 'போனை உங்கள் சூப்பர்வைசரிடம் திருப்பிக் கொடுங்கள்',
    giveSupervisor: 'போனை உங்கள் சூப்பர்வைசரிடம் கொடுங்கள்',
    reportDiscard: 'பதிவை நீக்கு', reportDiscardTitle: 'இந்தப் பதிவை நீக்கவா?', reportDiscardBody: 'உங்கள் சூப்பர்வைசர் இதைப் பார்க்க மாட்டார்.', reportDiscardConfirm: 'நீக்கு', reportKeep: 'வைத்திரு',
    consentWhat: 'உங்கள் பதிலைப் பதிவு செய்வோம்.', consentUse: 'உங்கள் குரல் இந்த நாட்டுக்கு வெளியே உள்ள கூகுள் கம்ப்யூட்டர்களுக்குப் போகும், இந்த விளக்கத்தைச் சரிபார்க்க மட்டும். சரிபார்த்த பிறகு, ஒரு நாளுக்குள் அழிக்கப்படும்.', consentAgree: 'சரி, சம்மதம்', consentNotNow: 'இப்போது வேண்டாம்',
  },
  bn: {
    start: 'শুরু করুন', listen: 'শুনুন', speak: 'এখন বলুন', done: 'শেষ', wait: 'অপেক্ষা করুন',
    readyHow: 'শুনুন। তারপর নিজের কথায় আবার বলুন।', readyKind: 'এটা আপনার পরীক্ষা নয়। কিছু পরিষ্কার না হলে, বলুন।', thanks: 'ধন্যবাদ',
    report: 'সমস্যা জানান', reportTitle: 'কী সমস্যা?', reportSpeak: 'বলে জানান', reportLimit: '৩০ সেকেন্ড পর্যন্ত', reportTap: 'কিছু না বলে পাঠান',
    reportRecording: 'রেকর্ড হচ্ছে। কী সমস্যা বলুন।', reportSend: 'পাঠান', reportCancel: 'বাতিল', reportSending: 'পাঠানো হচ্ছে…',
    reportSent: 'জানানোর জন্য ধন্যবাদ। আপনার সুপারভাইজার এটা দেখবেন।', reportFailed: 'পাঠানো যায়নি। আবার চেষ্টা করুন।', reportNoMic: 'মাইক কাজ করছে না। কিছু না বলেও পাঠাতে পারেন।',
    handBack: 'ফোনটা আপনার সুপারভাইজারকে ফেরত দিন',
    giveSupervisor: 'ফোনটা আপনার সুপারভাইজারকে দিন',
    reportDiscard: 'রিপোর্ট মুছুন', reportDiscardTitle: 'এই রিপোর্টটি মুছবেন?', reportDiscardBody: 'আপনার সুপারভাইজার এটা দেখতে পাবেন না।', reportDiscardConfirm: 'মুছুন', reportKeep: 'রেখে দিন',
    consentWhat: 'আমরা আপনার উত্তর রেকর্ড করব।', consentUse: 'আপনার গলার আওয়াজ এই দেশের বাইরে গুগলের কম্পিউটারে যাবে, শুধু এই কথাগুলো মিলিয়ে দেখার জন্য। মিলিয়ে দেখার পরে, এক দিনের মধ্যে মুছে ফেলা হবে।', consentAgree: 'আমি রাজি', consentNotNow: 'এখন না',
  },
  my: {
    start: 'စတင်ပါ', listen: 'နားထောင်ပါ', speak: 'ယခု ပြောပါ', done: 'ပြီးပါပြီ', wait: 'ခဏစောင့်ပါ',
    readyHow: 'နားထောင်ပါ။ ပြီးရင် ကိုယ့်စကားနဲ့ ပြန်ပြောပြပါ။', readyKind: 'ဒါ သင့်ကို စာမေးပွဲ စစ်တာ မဟုတ်ပါ။ တစ်ခုခု မရှင်းရင် ပြောပါ။', thanks: 'ကျေးဇူးတင်ပါတယ်',
    report: 'ပြဿနာ သတင်းပို့ပါ', reportTitle: 'ဘာပြဿနာလဲ။', reportSpeak: 'ပြောပြပါ', reportLimit: 'စက္ကန့် ၃၀ အထိ', reportTap: 'မပြောဘဲ ပို့ပါ',
    reportRecording: 'အသံဖမ်းနေသည်။ ပြဿနာကို ပြောပါ။', reportSend: 'ပို့ပါ', reportCancel: 'မလုပ်တော့ပါ', reportSending: 'ပို့နေသည်…',
    reportSent: 'ပြောပြတဲ့အတွက် ကျေးဇူးတင်ပါတယ်။ သင့်ကြီးကြပ်သူ ဒါကို မြင်ပါမယ်။', reportFailed: 'မပို့နိုင်ပါ။ ထပ်ကြိုးစားပါ။', reportNoMic: 'မိုက်ခရိုဖုန်း အလုပ်မလုပ်ပါ။ မပြောဘဲ ပို့နိုင်ပါသေးသည်။',
    handBack: 'ဖုန်းကို သင့်ကြီးကြပ်သူထံ ပြန်ပေးပါ',
    giveSupervisor: 'ဖုန်းကို သင့်ကြီးကြပ်သူထံ ပေးပါ',
    reportDiscard: 'သတင်းပို့ချက် ဖျက်ပါ', reportDiscardTitle: 'ဒီသတင်းပို့ချက်ကို ဖျက်မလား။', reportDiscardBody: 'သင့်ကြီးကြပ်သူ ဒါကို မမြင်ရပါ။', reportDiscardConfirm: 'ဖျက်ပါ', reportKeep: 'ထားပါ',
    consentWhat: 'သင့်အဖြေကို အသံဖမ်းပါမယ်။', consentUse: 'သင့်အသံကို ဒီနိုင်ငံပြင်ပမှာရှိတဲ့ ဂူဂဲလ်ကွန်ပျူတာတွေဆီ ပို့ပြီး ဒီရှင်းပြချက်ကို စစ်ဖို့ပဲ သုံးပါမယ်။ စစ်ပြီးရင် တစ်ရက်အတွင်း ဖျက်ပါမယ်။', consentAgree: 'သဘောတူပါတယ်', consentNotNow: 'အခု မလုပ်သေးပါ',
  },
  hi: {
    start: 'शुरू करें', listen: 'सुनिए', speak: 'अब बोलिए', done: 'हो गया', wait: 'कृपया रुकिए',
    readyHow: 'सुनिए। फिर अपने शब्दों में वापस बताइए।', readyKind: 'यह आपकी परीक्षा नहीं है। कुछ साफ़ न हो, तो बता दीजिए।', thanks: 'धन्यवाद',
    report: 'समस्या बताएँ', reportTitle: 'क्या गड़बड़ है?', reportSpeak: 'बोलकर बताएँ', reportLimit: '30 सेकंड तक', reportTap: 'बिना बोले भेजें',
    reportRecording: 'रिकॉर्ड हो रहा है। बताइए क्या गड़बड़ है।', reportSend: 'भेजें', reportCancel: 'रहने दें', reportSending: 'भेजा जा रहा है…',
    reportSent: 'बताने के लिए धन्यवाद। आपके सुपरवाइज़र इसे देखेंगे।', reportFailed: 'नहीं भेजा जा सका। फिर से कोशिश करें।', reportNoMic: 'माइक काम नहीं कर रहा। आप बिना बोले भी भेज सकते हैं।',
    handBack: 'फ़ोन अपने सुपरवाइज़र को वापस दे दीजिए',
    giveSupervisor: 'फ़ोन अपने सुपरवाइज़र को दे दीजिए',
    reportDiscard: 'रिपोर्ट हटाएँ', reportDiscardTitle: 'यह रिपोर्ट हटाएँ?', reportDiscardBody: 'आपके सुपरवाइज़र इसे नहीं देख पाएँगे।', reportDiscardConfirm: 'हटाएँ', reportKeep: 'रखें',
    consentWhat: 'हम आपका जवाब रिकॉर्ड करेंगे।', consentUse: 'आपकी आवाज़ देश के बाहर गूगल के कंप्यूटर पर जाएगी, सिर्फ़ इस बात को जाँचने के लिए। जाँच के बाद, एक दिन के अंदर मिटा दी जाएगी।', consentAgree: 'मैं राज़ी हूँ', consentNotNow: 'अभी नहीं',
  },
  or: {
    start: 'ଆରମ୍ଭ କରନ୍ତୁ', listen: 'ଶୁଣନ୍ତୁ', speak: 'ଏବେ କୁହନ୍ତୁ', done: 'ହୋଇଗଲା', wait: 'ଅପେକ୍ଷା କରନ୍ତୁ',
    readyHow: 'ଶୁଣନ୍ତୁ। ତା’ପରେ ନିଜ କଥାରେ ପୁଣି କୁହନ୍ତୁ।', readyKind: 'ଏହା ଆପଣଙ୍କ ପରୀକ୍ଷା ନୁହେଁ। କିଛି ସ୍ପଷ୍ଟ ନହେଲେ, କୁହନ୍ତୁ।', thanks: 'ଧନ୍ୟବାଦ',
    report: 'ସମସ୍ୟା ଜଣାନ୍ତୁ', reportTitle: 'କଣ ସମସ୍ୟା?', reportSpeak: 'କହି ଜଣାନ୍ତୁ', reportLimit: '୩୦ ସେକେଣ୍ଡ ପର୍ଯ୍ୟନ୍ତ', reportTap: 'ନ କହି ପଠାନ୍ତୁ',
    reportRecording: 'ରେକର୍ଡ ହେଉଛି। କଣ ସମସ୍ୟା କୁହନ୍ତୁ।', reportSend: 'ପଠାନ୍ତୁ', reportCancel: 'ବାତିଲ', reportSending: 'ପଠାଯାଉଛି…',
    reportSent: 'ଜଣାଇଥିବାରୁ ଧନ୍ୟବାଦ। ଆପଣଙ୍କ ସୁପରଭାଇଜର ଏହା ଦେଖିବେ।', reportFailed: 'ପଠାଯାଇପାରିଲା ନାହିଁ। ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ।', reportNoMic: 'ମାଇକ କାମ କରୁନାହିଁ। ନ କହି ମଧ୍ୟ ପଠାଇପାରିବେ।',
    handBack: 'ଫୋନଟି ଆପଣଙ୍କ ସୁପରଭାଇଜରଙ୍କୁ ଫେରାଇ ଦିଅନ୍ତୁ',
    giveSupervisor: 'ଫୋନଟି ଆପଣଙ୍କ ସୁପରଭାଇଜରଙ୍କୁ ଦିଅନ୍ତୁ',
    reportDiscard: 'ରିପୋର୍ଟ ବିଲୋପ କରନ୍ତୁ', reportDiscardTitle: 'ଏହି ରିପୋର୍ଟ ବିଲୋପ କରିବେ?', reportDiscardBody: 'ଆପଣଙ୍କ ସୁପରଭାଇଜର ଏହା ଦେଖିପାରିବେ ନାହିଁ।', reportDiscardConfirm: 'ବିଲୋପ କରନ୍ତୁ', reportKeep: 'ରଖନ୍ତୁ',
    consentWhat: 'ଆମେ ଆପଣଙ୍କ ଉତ୍ତର ରେକର୍ଡ କରିବୁ।', consentUse: 'ଆପଣଙ୍କ ସ୍ୱର ଦେଶ ବାହାରେ ଥିବା ଗୁଗଲର କମ୍ପ୍ୟୁଟରକୁ ଯିବ, କେବଳ ଏହି କଥା ଯାଞ୍ଚ ପାଇଁ। ଯାଞ୍ଚ ପରେ, ଏକ ଦିନ ଭିତରେ ବିଲୋପ କରାଯିବ।', consentAgree: 'ମୁଁ ରାଜି', consentNotNow: 'ଏବେ ନୁହେଁ',
  },
  te: {
    start: 'మొదలుపెట్టండి', listen: 'వినండి', speak: 'ఇప్పుడు మాట్లాడండి', done: 'అయిపోయింది', wait: 'కొంచెం ఆగండి',
    readyHow: 'వినండి. తర్వాత మీ సొంత మాటల్లో తిరిగి చెప్పండి.', readyKind: 'ఇది మీకు పరీక్ష కాదు. ఏదైనా స్పష్టంగా లేకపోతే, చెప్పండి.', thanks: 'ధన్యవాదాలు',
    report: 'సమస్య చెప్పండి', reportTitle: 'ఏం సమస్య?', reportSpeak: 'మాట్లాడి చెప్పండి', reportLimit: '30 సెకన్ల వరకు', reportTap: 'మాట్లాడకుండా పంపండి',
    reportRecording: 'రికార్డ్ అవుతోంది. ఏం సమస్యో చెప్పండి.', reportSend: 'పంపండి', reportCancel: 'వద్దు', reportSending: 'పంపుతోంది…',
    reportSent: 'చెప్పినందుకు ధన్యవాదాలు. మీ సూపర్‌వైజర్ దీన్ని చూస్తారు.', reportFailed: 'పంపలేకపోయాం. మళ్ళీ ప్రయత్నించండి.', reportNoMic: 'మైక్ పనిచేయడం లేదు. మాట్లాడకుండా కూడా పంపవచ్చు.',
    handBack: 'ఫోన్‌ను మీ సూపర్‌వైజర్‌కు తిరిగి ఇవ్వండి',
    giveSupervisor: 'ఫోన్‌ను మీ సూపర్‌వైజర్‌కు ఇవ్వండి',
    reportDiscard: 'రిపోర్ట్ తీసేయండి', reportDiscardTitle: 'ఈ రిపోర్ట్ తీసేయాలా?', reportDiscardBody: 'మీ సూపర్‌వైజర్ దీన్ని చూడలేరు.', reportDiscardConfirm: 'తీసేయండి', reportKeep: 'ఉంచండి',
    consentWhat: 'మీ జవాబులను రికార్డ్ చేస్తాం.', consentUse: 'మీ గొంతు దేశం బయట ఉన్న గూగుల్ కంప్యూటర్లకు వెళ్తుంది, ఈ విషయం సరిచూడటానికి మాత్రమే. సరిచూసిన తర్వాత, ఒక రోజులోపు తొలగిస్తాం.', consentAgree: 'ఒప్పుకుంటాను', consentNotNow: 'ఇప్పుడు వద్దు',
  },
}
