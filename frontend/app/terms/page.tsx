"use client";

import Link from "next/link";
import { useState } from "react";
import Logo from "@/components/Logo";

type Lang = "en" | "vi";

interface Section {
  heading: { en: string; vi: string };
  body: { en: string[]; vi: string[] };
}

const LAST_UPDATED = {
  en: "Last updated: 16 May 2026",
  vi: "Cập nhật lần cuối: 16/05/2026",
};

const INTRO: Section["body"] = {
  en: [
    "Welcome to Confluex (the “Service”), an automated literature review platform that searches scholarly sources, summarizes papers, and helps you draft research writing. By creating an account, signing in with Google, or otherwise using the Service, you agree to be bound by these Terms of Usage (the “Terms”). If you do not agree, do not use the Service.",
  ],
  vi: [
    "Chào mừng bạn đến với Confluex (“Dịch vụ”) — nền tảng tổng quan tài liệu khoa học tự động, hỗ trợ tìm kiếm nguồn học thuật, tóm tắt bài báo và soạn thảo nội dung nghiên cứu. Khi tạo tài khoản, đăng nhập bằng Google hoặc sử dụng Dịch vụ theo bất kỳ hình thức nào, bạn xác nhận đã đồng ý với các Điều khoản Sử dụng này (“Điều khoản”). Nếu không đồng ý, vui lòng không sử dụng Dịch vụ.",
  ],
};

const SECTIONS: Section[] = [
  {
    heading: { en: "1. Eligibility", vi: "1. Đối tượng sử dụng" },
    body: {
      en: [
        "You must be at least 16 years old, or the age of digital consent in your jurisdiction, to use the Service. By using the Service, you represent that the information you provide at registration is accurate and that you have the authority to accept these Terms on behalf of yourself or the organization you represent.",
      ],
      vi: [
        "Bạn phải đủ 16 tuổi trở lên, hoặc đạt độ tuổi đồng thuận số theo quy định pháp luật nơi bạn sinh sống, để sử dụng Dịch vụ. Khi sử dụng Dịch vụ, bạn cam đoan rằng các thông tin đăng ký là chính xác và bạn có thẩm quyền chấp nhận các Điều khoản này cho chính mình hoặc tổ chức mà bạn đại diện.",
      ],
    },
  },
  {
    heading: { en: "2. Accounts and Security", vi: "2. Tài khoản và bảo mật" },
    body: {
      en: [
        "You are responsible for keeping your password and authentication credentials confidential. Sharing accounts, allowing automated agents you do not control to sign in on your behalf, or attempting to access another user’s workspace is prohibited.",
        "Notify us immediately if you suspect unauthorized access. We may suspend or terminate accounts that we reasonably believe have been compromised or used to abuse the Service.",
      ],
      vi: [
        "Bạn có trách nhiệm bảo mật mật khẩu và thông tin xác thực của mình. Việc chia sẻ tài khoản, để các tác nhân tự động không thuộc kiểm soát của bạn đăng nhập thay bạn, hoặc cố ý truy cập vào không gian làm việc của người dùng khác đều bị cấm.",
        "Vui lòng thông báo ngay cho chúng tôi nếu nghi ngờ tài khoản bị truy cập trái phép. Chúng tôi có quyền tạm ngừng hoặc chấm dứt các tài khoản mà chúng tôi có cơ sở hợp lý để cho rằng đã bị xâm phạm hoặc bị sử dụng để vi phạm Dịch vụ.",
      ],
    },
  },
  {
    heading: { en: "3. Credits, Billing, and Refunds", vi: "3. Tín dụng, thanh toán và hoàn tiền" },
    body: {
      en: [
        "New accounts receive a one-time grant of free credits. Additional credits can be purchased through SePay/VietQR using the credit packs listed on the billing page. Credits are required to run the discovery pipeline, paper conversations, Deep Search, writer generation, and reference uploads.",
        "Credits are non-transferable and have no cash value outside the Service. Purchased credits do not expire unless we provide at least 30 days’ notice. We may grant promotional or administrative credits at our discretion; these may carry shorter expiry windows.",
        "If a paid operation fails for a reason attributable to the Service, the credits debited for that operation will be refunded to your ledger automatically. We do not issue cash refunds for credits already consumed by successful operations.",
      ],
      vi: [
        "Tài khoản mới được tặng một lần tín dụng miễn phí. Bạn có thể nạp thêm tín dụng qua SePay/VietQR theo các gói được liệt kê trên trang thanh toán. Tín dụng được dùng cho các tính năng có tính phí: pipeline khám phá, hội thoại theo bài báo, Deep Search, sinh nội dung Writer và tải lên tài liệu tham khảo.",
        "Tín dụng không thể chuyển nhượng và không có giá trị tiền mặt ngoài phạm vi Dịch vụ. Tín dụng đã mua không hết hạn trừ khi chúng tôi thông báo trước ít nhất 30 ngày. Tín dụng khuyến mãi hoặc tín dụng cấp quản trị có thể có thời hạn ngắn hơn.",
        "Nếu một thao tác có tính phí thất bại do lỗi từ phía Dịch vụ, số tín dụng đã trừ cho thao tác đó sẽ được hoàn lại tự động vào sổ tín dụng của bạn. Chúng tôi không hoàn tiền mặt cho tín dụng đã được sử dụng thành công.",
      ],
    },
  },
  {
    heading: { en: "4. Acceptable Use", vi: "4. Quy tắc sử dụng" },
    body: {
      en: [
        "You agree not to: (a) reverse engineer or attempt to extract source code, prompts, or model weights from the Service; (b) use the Service to generate content that is unlawful, defamatory, harassing, discriminatory, or that infringes intellectual-property rights; (c) submit content that contains personal data of others without a lawful basis; (d) circumvent rate limits, credit metering, or admin allowlists; (e) use the Service to build a competing product by scraping outputs at scale.",
        "Academic integrity remains your responsibility. You must comply with the rules of any institution, journal, or conference you submit work to, including disclosure of AI-assisted writing where required.",
      ],
      vi: [
        "Bạn cam kết không: (a) dịch ngược, cố gắng trích xuất mã nguồn, prompt hoặc trọng số mô hình của Dịch vụ; (b) sử dụng Dịch vụ để tạo nội dung trái pháp luật, bôi nhọ, quấy rối, phân biệt đối xử hoặc xâm phạm quyền sở hữu trí tuệ; (c) gửi nội dung chứa dữ liệu cá nhân của người khác khi không có cơ sở pháp lý; (d) né tránh giới hạn tốc độ, hạn mức tín dụng hoặc danh sách quản trị; (e) sử dụng Dịch vụ để xây dựng sản phẩm cạnh tranh bằng cách thu thập đầu ra ở quy mô lớn.",
        "Liêm chính học thuật vẫn thuộc trách nhiệm của bạn. Bạn phải tuân thủ quy định của bất kỳ tổ chức, tạp chí hoặc hội nghị nào bạn gửi bài, bao gồm việc khai báo phần nội dung được hỗ trợ bởi AI nếu có yêu cầu.",
      ],
    },
  },
  {
    heading: { en: "5. Content and Intellectual Property", vi: "5. Nội dung và sở hữu trí tuệ" },
    body: {
      en: [
        "You retain ownership of the prompts, queries, and reference documents you submit (“Your Content”). You grant us a limited, worldwide, royalty-free license to process Your Content solely to operate, secure, and improve the Service.",
        "Outputs generated by the Service are provided to you for your research purposes. Some outputs incorporate metadata, abstracts, or excerpts from third-party sources such as Semantic Scholar and arXiv; your use of those materials remains subject to the licenses and terms of the original publishers.",
        "We retain all rights to the Service, including the software, UI, brand, and aggregated, de-identified usage data used to improve the platform.",
      ],
      vi: [
        "Bạn giữ quyền sở hữu đối với các prompt, truy vấn và tài liệu tham khảo mà bạn cung cấp (“Nội dung của bạn”). Bạn cấp cho chúng tôi quyền sử dụng có giới hạn, trên toàn cầu, miễn phí bản quyền để xử lý Nội dung của bạn duy nhất cho mục đích vận hành, bảo mật và cải thiện Dịch vụ.",
        "Các đầu ra do Dịch vụ tạo ra được cung cấp cho mục đích nghiên cứu của bạn. Một số đầu ra có chứa metadata, tóm tắt hoặc trích đoạn từ các nguồn bên thứ ba như Semantic Scholar và arXiv; việc bạn sử dụng các tư liệu đó vẫn phải tuân thủ giấy phép và điều khoản của nhà xuất bản gốc.",
        "Chúng tôi giữ toàn bộ quyền đối với Dịch vụ, bao gồm phần mềm, giao diện, thương hiệu và dữ liệu sử dụng đã được tổng hợp, ẩn danh để cải thiện nền tảng.",
      ],
    },
  },
  {
    heading: { en: "6. AI Output Disclaimer", vi: "6. Tuyên bố về đầu ra AI" },
    body: {
      en: [
        "The Service uses large language models and embedding models to summarize, rank, and draft text. Outputs may contain factual errors, hallucinated citations, or biased framing. You are responsible for verifying any claim, citation, or quotation before relying on it for academic, clinical, legal, financial, or other consequential decisions.",
        "We make no guarantee that AI-generated outputs are original, non-infringing, or fit for a particular purpose.",
      ],
      vi: [
        "Dịch vụ sử dụng các mô hình ngôn ngữ lớn và mô hình embedding để tóm tắt, xếp hạng và soạn thảo văn bản. Đầu ra có thể chứa lỗi sự thật, trích dẫn ảo hoặc cách diễn giải thiên lệch. Bạn có trách nhiệm xác minh mọi tuyên bố, trích dẫn hoặc câu trích trước khi sử dụng vào các quyết định học thuật, y tế, pháp lý, tài chính hoặc quan trọng khác.",
        "Chúng tôi không bảo đảm rằng các đầu ra do AI tạo ra là nguyên gốc, không vi phạm quyền của bên thứ ba, hoặc phù hợp cho một mục đích cụ thể.",
      ],
    },
  },
  {
    heading: { en: "7. Privacy", vi: "7. Quyền riêng tư" },
    body: {
      en: [
        "We store your email, password hash (or Google OAuth identifier), uploaded reference files, projects, and conversation history so the Service can function. Prompts and reference content are sent to upstream model providers (such as OpenRouter) for inference; we do not sell your data to advertisers.",
        "You can request deletion of your account and associated data by contacting us. Some aggregated and de-identified logs may be retained for security and abuse-prevention purposes.",
      ],
      vi: [
        "Chúng tôi lưu trữ email, hash mật khẩu (hoặc định danh Google OAuth), tệp tham khảo đã tải lên, các dự án và lịch sử hội thoại của bạn để Dịch vụ có thể vận hành. Prompt và nội dung tham khảo được gửi đến các nhà cung cấp mô hình thượng nguồn (ví dụ OpenRouter) để suy luận; chúng tôi không bán dữ liệu của bạn cho các đơn vị quảng cáo.",
        "Bạn có thể yêu cầu xóa tài khoản và dữ liệu liên quan bằng cách liên hệ với chúng tôi. Một số nhật ký đã được tổng hợp và ẩn danh có thể được lưu lại vì mục đích bảo mật và chống lạm dụng.",
      ],
    },
  },
  {
    heading: { en: "8. Suspension and Termination", vi: "8. Tạm ngừng và chấm dứt" },
    body: {
      en: [
        "We may suspend or terminate your access if you violate these Terms, fail to pay for credits, or use the Service in a way that risks harm to other users or the platform. You may stop using the Service at any time; remaining unused credits do not become refundable to cash upon termination unless required by law.",
      ],
      vi: [
        "Chúng tôi có quyền tạm ngừng hoặc chấm dứt quyền truy cập của bạn nếu bạn vi phạm các Điều khoản này, không thanh toán cho tín dụng, hoặc sử dụng Dịch vụ theo cách gây rủi ro cho người dùng khác hoặc cho nền tảng. Bạn có thể ngừng sử dụng Dịch vụ bất kỳ lúc nào; số tín dụng chưa sử dụng còn lại sẽ không được hoàn lại bằng tiền mặt khi chấm dứt, trừ khi pháp luật yêu cầu.",
      ],
    },
  },
  {
    heading: { en: "9. Disclaimers and Limitation of Liability", vi: "9. Tuyên bố miễn trừ và giới hạn trách nhiệm" },
    body: {
      en: [
        "The Service is provided “as is” and “as available”, without warranties of any kind, whether express or implied, including warranties of merchantability, fitness for a particular purpose, or non-infringement.",
        "To the maximum extent permitted by law, our aggregate liability arising out of or relating to the Service in any 12-month period will not exceed the amount you paid us for credits during that period. We are not liable for indirect, incidental, consequential, or punitive damages, including loss of data, loss of academic standing, or lost research output.",
      ],
      vi: [
        "Dịch vụ được cung cấp theo nguyên trạng (“as is”) và theo trạng thái sẵn có (“as available”), không kèm theo bất kỳ bảo đảm nào, dù tường minh hay ngầm định, bao gồm bảo đảm về khả năng kinh doanh, tính phù hợp cho mục đích cụ thể hoặc tính không vi phạm.",
        "Trong giới hạn tối đa được pháp luật cho phép, trách nhiệm tổng hợp của chúng tôi phát sinh từ hoặc liên quan đến Dịch vụ trong bất kỳ giai đoạn 12 tháng nào sẽ không vượt quá tổng số tiền bạn đã thanh toán cho tín dụng trong giai đoạn đó. Chúng tôi không chịu trách nhiệm về các thiệt hại gián tiếp, ngẫu nhiên, hệ quả hoặc trừng phạt, bao gồm mất dữ liệu, mất uy tín học thuật hoặc mất kết quả nghiên cứu.",
      ],
    },
  },
  {
    heading: { en: "10. Changes to These Terms", vi: "10. Thay đổi các Điều khoản" },
    body: {
      en: [
        "We may update these Terms to reflect changes in the Service, the law, or our business. Material changes will be announced through the app or by email at least 14 days before they take effect. Continued use of the Service after the effective date constitutes acceptance of the revised Terms.",
      ],
      vi: [
        "Chúng tôi có thể cập nhật các Điều khoản này để phản ánh thay đổi trong Dịch vụ, pháp luật hoặc hoạt động kinh doanh. Các thay đổi quan trọng sẽ được thông báo qua ứng dụng hoặc email ít nhất 14 ngày trước khi có hiệu lực. Việc bạn tiếp tục sử dụng Dịch vụ sau ngày có hiệu lực được xem là chấp nhận các Điều khoản đã sửa đổi.",
      ],
    },
  },
  {
    heading: { en: "11. Governing Law", vi: "11. Luật áp dụng" },
    body: {
      en: [
        "These Terms are governed by the laws of the Socialist Republic of Vietnam, without regard to conflict-of-laws principles. Disputes will be resolved in the competent courts of Hanoi, unless mandatory consumer-protection rules in your jurisdiction provide otherwise.",
      ],
      vi: [
        "Các Điều khoản này được điều chỉnh theo pháp luật nước Cộng hòa Xã hội Chủ nghĩa Việt Nam, không áp dụng các nguyên tắc xung đột pháp luật. Tranh chấp sẽ được giải quyết tại tòa án có thẩm quyền tại Hà Nội, trừ trường hợp các quy định bảo vệ người tiêu dùng mang tính bắt buộc tại nơi cư trú của bạn quy định khác.",
      ],
    },
  },
  {
    heading: { en: "12. Contact", vi: "12. Liên hệ" },
    body: {
      en: [
        "Questions about these Terms can be sent to support@confluex.app. For data-deletion or privacy requests, please use the same address and include the email associated with your account.",
      ],
      vi: [
        "Mọi câu hỏi về Điều khoản này có thể gửi đến support@confluex.app. Với yêu cầu xóa dữ liệu hoặc liên quan đến quyền riêng tư, vui lòng dùng cùng địa chỉ trên và kèm email tài khoản của bạn.",
      ],
    },
  },
];

const UI = {
  en: {
    title: "Terms of Usage",
    toggle: "Tiếng Việt",
    backToSignup: "Back to sign up",
  },
  vi: {
    title: "Điều khoản Sử dụng",
    toggle: "English",
    backToSignup: "Quay lại đăng ký",
  },
} as const;

export default function TermsPage() {
  const [lang, setLang] = useState<Lang>("en");
  const t = UI[lang];

  return (
    <main className="min-h-screen bg-background font-ui text-on-surface">
      <header className="sticky top-0 z-10 border-b border-outline/20 bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-6 py-4">
          <Link href="/" className="flex items-center gap-2">
            <Logo size="sm" />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="rounded-lg border border-outline/40 px-3 py-1.5 text-xs text-on-surface-variant transition hover:border-primary hover:text-primary"
            >
              {t.backToSignup}
            </Link>
            <button
              type="button"
              onClick={() => setLang(lang === "en" ? "vi" : "en")}
              aria-label="Toggle language"
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white transition hover:bg-primary/90"
            >
              {t.toggle}
            </button>
          </div>
        </div>
      </header>

      <article className="mx-auto max-w-3xl space-y-8 px-6 py-10">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">{t.title}</h1>
          <p className="text-xs text-hint">{LAST_UPDATED[lang]}</p>
        </div>

        <div className="space-y-4 text-sm leading-relaxed text-on-surface-variant">
          {INTRO[lang].map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>

        {SECTIONS.map((section) => (
          <section key={section.heading.en} className="space-y-3">
            <h2 className="text-lg font-semibold text-on-surface">{section.heading[lang]}</h2>
            <div className="space-y-3 text-sm leading-relaxed text-on-surface-variant">
              {section.body[lang].map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          </section>
        ))}

        <div className="pt-6">
          <Link
            href="/login"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            ← {t.backToSignup}
          </Link>
        </div>
      </article>
    </main>
  );
}
