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
  en: "Last updated: 17 May 2026",
  vi: "Cập nhật lần cuối: 17/05/2026",
};

const INTRO: Section["body"] = {
  en: [
    "This Privacy Policy explains how Confluex (the “Service”) collects, uses, stores, and shares information when you create an account, search for papers, run the discovery pipeline, chat with papers, or generate writing through the Service. It supplements the Terms of Service and should be read together with them.",
    "We aim to collect the minimum data needed to operate the Service, keep it secure, and improve quality. We do not sell your personal data.",
  ],
  vi: [
    "Chính sách Bảo mật này giải thích cách Confluex (“Dịch vụ”) thu thập, sử dụng, lưu trữ và chia sẻ thông tin khi bạn tạo tài khoản, tìm kiếm bài báo, chạy pipeline khám phá, trò chuyện với bài báo hoặc tạo nội dung viết thông qua Dịch vụ. Chính sách này bổ sung cho Điều khoản Dịch vụ và cần được đọc kèm với điều khoản đó.",
    "Chúng tôi cố gắng thu thập tối thiểu dữ liệu cần thiết để vận hành Dịch vụ, đảm bảo an toàn và cải thiện chất lượng. Chúng tôi không bán dữ liệu cá nhân của bạn.",
  ],
};

const SECTIONS: Section[] = [
  {
    heading: { en: "1. Information We Collect", vi: "1. Thông tin chúng tôi thu thập" },
    body: {
      en: [
        "Account data: email address, password hash, or - for Google sign-in - your Google account identifier and basic profile (name, picture).",
        "Usage data: prompts and queries you submit, project metadata, conversation history, reference files you upload, writer drafts, and feedback signals (such as the helpful/not-helpful buttons on AI replies).",
        "Billing data: SePay/VietQR payment references and ledger entries for credit purchases and consumption. We do not store full card numbers.",
        "Technical data: IP address, browser user agent, request timestamps, and server logs collected automatically when you use the Service.",
      ],
      vi: [
        "Dữ liệu tài khoản: địa chỉ email, hash mật khẩu, hoặc - với đăng nhập Google - định danh tài khoản Google và thông tin hồ sơ cơ bản (tên, ảnh đại diện).",
        "Dữ liệu sử dụng: các prompt và truy vấn bạn gửi, metadata dự án, lịch sử hội thoại, tệp tham khảo bạn tải lên, bản nháp Writer, và các tín hiệu phản hồi (ví dụ nút hữu ích / không hữu ích trên câu trả lời của AI).",
        "Dữ liệu thanh toán: tham chiếu thanh toán SePay/VietQR và sổ ghi cho việc mua/sử dụng tín dụng. Chúng tôi không lưu số thẻ đầy đủ.",
        "Dữ liệu kỹ thuật: địa chỉ IP, user agent của trình duyệt, dấu thời gian yêu cầu và nhật ký máy chủ được thu thập tự động khi bạn sử dụng Dịch vụ.",
      ],
    },
  },
  {
    heading: { en: "2. Free Tier and Telemetry", vi: "2. Gói miễn phí và dữ liệu cải thiện sản phẩm" },
    body: {
      en: [
        "If you use the Service on the free tier (no paid credits or admin allowlist), you agree that your prompts, generated outputs, and feedback signals (likes, dislikes, copy actions, and similar interactions) may be retained and analyzed to improve model quality, ranking heuristics, and product features.",
        "We use this data internally and with our model-inference providers (such as OpenRouter) only as needed to deliver and improve the Service. Where feasible, telemetry is aggregated or de-identified before use in dashboards or analysis.",
        "Paid-tier accounts have the same default behavior, but you may request that your prompts and outputs be excluded from product-improvement analysis by contacting us. Telemetry kept strictly for security, abuse prevention, billing, and legal compliance cannot be opted out of.",
      ],
      vi: [
        "Nếu bạn sử dụng Dịch vụ ở gói miễn phí (không có tín dụng đã thanh toán hoặc không thuộc danh sách quản trị), bạn đồng ý rằng các prompt, đầu ra do AI tạo ra và các tín hiệu phản hồi (thích, không thích, sao chép và các tương tác tương tự) có thể được lưu lại và phân tích để cải thiện chất lượng mô hình, thuật toán xếp hạng và tính năng sản phẩm.",
        "Chúng tôi sử dụng dữ liệu này nội bộ và với các nhà cung cấp mô hình suy luận (ví dụ OpenRouter) chỉ trong phạm vi cần thiết để vận hành và cải thiện Dịch vụ. Khi khả thi, dữ liệu cải thiện sản phẩm sẽ được tổng hợp hoặc ẩn danh trước khi đưa vào bảng điều khiển hoặc phân tích.",
        "Tài khoản gói trả phí có hành vi mặc định tương tự, nhưng bạn có thể yêu cầu loại trừ prompt và đầu ra khỏi quá trình phân tích cải thiện sản phẩm bằng cách liên hệ với chúng tôi. Dữ liệu được giữ lại nghiêm ngặt vì mục đích bảo mật, chống lạm dụng, thanh toán và tuân thủ pháp luật không thể được loại trừ.",
      ],
    },
  },
  {
    heading: { en: "3. How We Use Your Information", vi: "3. Cách chúng tôi sử dụng thông tin" },
    body: {
      en: [
        "To provide the Service: authenticate you, run search and summarization pipelines, serve paper chats, generate writer drafts, and apply credit-based metering.",
        "To improve the Service: analyze feedback, identify regressions, evaluate prompt and ranking changes, and train internal evaluation sets.",
        "To secure the Service: detect abuse, rate-limit attackers, investigate incidents, and comply with legal requirements.",
        "To communicate with you: send transactional emails (password resets, billing receipts) and important Service announcements.",
      ],
      vi: [
        "Để cung cấp Dịch vụ: xác thực bạn, vận hành pipeline tìm kiếm và tóm tắt, phục vụ trò chuyện với bài báo, tạo bản nháp Writer và áp dụng hạn mức tín dụng.",
        "Để cải thiện Dịch vụ: phân tích phản hồi, phát hiện hồi quy, đánh giá thay đổi prompt và xếp hạng, và xây dựng bộ đánh giá nội bộ.",
        "Để bảo mật Dịch vụ: phát hiện lạm dụng, giới hạn tốc độ tấn công, điều tra sự cố và tuân thủ yêu cầu pháp lý.",
        "Để liên lạc với bạn: gửi email giao dịch (đặt lại mật khẩu, biên lai thanh toán) và các thông báo quan trọng về Dịch vụ.",
      ],
    },
  },
  {
    heading: { en: "4. How We Share Your Information", vi: "4. Cách chúng tôi chia sẻ thông tin" },
    body: {
      en: [
        "Model providers: prompts and reference content are forwarded to upstream inference and embedding providers (such as OpenRouter) so the Service can return results. These providers process data under their own terms; we choose providers that contractually limit training on customer prompts where available.",
        "Scholarly source APIs: we send your queries to Semantic Scholar and arXiv to retrieve papers. We do not send your email or account identifier with those queries.",
        "Payment provider: SePay processes VietQR transactions. We share the reference code, amount, and currency needed to settle your order; we do not share your prompts or research content with SePay.",
        "Service providers and infrastructure: hosting, database, error tracking, and email-delivery vendors process data on our behalf under data-processing agreements.",
        "Legal requirements: we may disclose information when required by valid legal process or to protect the rights, property, or safety of users or the public.",
        "We do not sell your personal data, and we do not share it with advertisers.",
      ],
      vi: [
        "Nhà cung cấp mô hình: prompt và nội dung tham khảo được chuyển đến các nhà cung cấp suy luận và embedding thượng nguồn (ví dụ OpenRouter) để Dịch vụ có thể trả kết quả. Các nhà cung cấp này xử lý dữ liệu theo điều khoản riêng của họ; chúng tôi ưu tiên các nhà cung cấp có cam kết hợp đồng giới hạn việc huấn luyện trên prompt của khách hàng khi có thể.",
        "API nguồn học thuật: chúng tôi gửi truy vấn của bạn đến Semantic Scholar và arXiv để lấy bài báo. Chúng tôi không gửi email hoặc định danh tài khoản của bạn cùng với các truy vấn đó.",
        "Nhà cung cấp thanh toán: SePay xử lý các giao dịch VietQR. Chúng tôi chỉ chia sẻ mã tham chiếu, số tiền và đơn vị tiền tệ cần thiết để xử lý đơn hàng; chúng tôi không chia sẻ prompt hay nội dung nghiên cứu với SePay.",
        "Nhà cung cấp dịch vụ và hạ tầng: các bên cung cấp hosting, cơ sở dữ liệu, theo dõi lỗi và gửi email xử lý dữ liệu thay mặt chúng tôi theo các thỏa thuận xử lý dữ liệu.",
        "Yêu cầu pháp lý: chúng tôi có thể tiết lộ thông tin khi được yêu cầu bởi tiến trình pháp lý hợp lệ hoặc để bảo vệ quyền, tài sản, an toàn của người dùng hoặc công chúng.",
        "Chúng tôi không bán dữ liệu cá nhân của bạn và không chia sẻ dữ liệu đó với các đơn vị quảng cáo.",
      ],
    },
  },
  {
    heading: { en: "5. Data Retention", vi: "5. Thời gian lưu trữ dữ liệu" },
    body: {
      en: [
        "Account, project, conversation, and reference data are retained for as long as your account is active.",
        "If you delete your account, your personal data and project content are removed within 30 days, except for records we are required to keep for legal, tax, accounting, or security reasons (typically up to 5 years).",
        "Aggregated and de-identified analytics may be retained indefinitely because they cannot reasonably be linked back to you.",
      ],
      vi: [
        "Dữ liệu tài khoản, dự án, hội thoại và tham khảo được lưu trữ trong suốt thời gian tài khoản của bạn còn hoạt động.",
        "Nếu bạn xóa tài khoản, dữ liệu cá nhân và nội dung dự án của bạn sẽ được xóa trong vòng 30 ngày, trừ các hồ sơ mà chúng tôi buộc phải giữ vì lý do pháp lý, thuế, kế toán hoặc bảo mật (thường tối đa 5 năm).",
        "Dữ liệu phân tích đã được tổng hợp và ẩn danh có thể được lưu giữ vô thời hạn vì không thể truy ngược về bạn một cách hợp lý.",
      ],
    },
  },
  {
    heading: { en: "6. Your Rights", vi: "6. Quyền của bạn" },
    body: {
      en: [
        "Subject to applicable law (including Vietnam’s Decree 13/2023 on Personal Data Protection and the EU GDPR where it applies), you have the right to: access your personal data, request correction, request deletion, restrict or object to certain processing, withdraw consent for optional uses, and export the data you provided in a portable format.",
        "To exercise these rights, contact support@confluex.app from the email associated with your account. We will respond within 30 days. If we cannot verify your identity or your request conflicts with a legal obligation, we will explain why.",
      ],
      vi: [
        "Tuân thủ pháp luật áp dụng (bao gồm Nghị định 13/2023/NĐ-CP về Bảo vệ Dữ liệu Cá nhân tại Việt Nam và GDPR của EU khi áp dụng), bạn có quyền: truy cập dữ liệu cá nhân của mình, yêu cầu chỉnh sửa, yêu cầu xóa, hạn chế hoặc phản đối một số hoạt động xử lý, rút lại đồng ý cho các mục đích sử dụng tùy chọn, và xuất dữ liệu bạn đã cung cấp dưới định dạng có thể chuyển đổi.",
        "Để thực hiện các quyền này, vui lòng liên hệ support@confluex.app từ email gắn với tài khoản của bạn. Chúng tôi sẽ phản hồi trong vòng 30 ngày. Nếu không thể xác minh danh tính của bạn hoặc yêu cầu của bạn xung đột với nghĩa vụ pháp lý, chúng tôi sẽ giải thích lý do.",
      ],
    },
  },
  {
    heading: { en: "7. Data Security", vi: "7. An toàn dữ liệu" },
    body: {
      en: [
        "We protect data with encryption in transit (HTTPS), hashed password storage, scoped database access, audit logging, and credentialed admin access. No system is perfectly secure; we will notify affected users without undue delay if we discover a breach that materially affects them.",
      ],
      vi: [
        "Chúng tôi bảo vệ dữ liệu bằng mã hóa khi truyền (HTTPS), lưu mật khẩu dưới dạng hash, kiểm soát truy cập cơ sở dữ liệu theo phạm vi, ghi nhật ký kiểm toán và truy cập quản trị có xác thực. Không hệ thống nào tuyệt đối an toàn; chúng tôi sẽ thông báo cho người dùng bị ảnh hưởng mà không có sự chậm trễ vô lý nếu phát hiện sự cố ảnh hưởng đáng kể đến họ.",
      ],
    },
  },
  {
    heading: { en: "8. International Transfers", vi: "8. Chuyển dữ liệu quốc tế" },
    body: {
      en: [
        "Some of our service providers operate outside Vietnam. When we transfer personal data abroad, we rely on contractual safeguards (such as standard data-protection clauses) and on providers with industry-standard security practices. By using the Service, you acknowledge that your information may be processed in countries with data-protection regimes different from those of your home country.",
      ],
      vi: [
        "Một số nhà cung cấp dịch vụ của chúng tôi hoạt động ngoài Việt Nam. Khi chuyển dữ liệu cá nhân ra nước ngoài, chúng tôi dựa vào các biện pháp bảo vệ theo hợp đồng (ví dụ điều khoản bảo vệ dữ liệu tiêu chuẩn) và các nhà cung cấp có thực hành bảo mật phù hợp tiêu chuẩn ngành. Bằng việc sử dụng Dịch vụ, bạn xác nhận rằng thông tin của mình có thể được xử lý tại các quốc gia có chế độ bảo vệ dữ liệu khác với quốc gia cư trú của bạn.",
      ],
    },
  },
  {
    heading: { en: "9. Children", vi: "9. Trẻ em" },
    body: {
      en: [
        "The Service is not directed to children under 16. If we learn we have collected personal data from a child without verifiable parental consent, we will delete that data.",
      ],
      vi: [
        "Dịch vụ không hướng đến trẻ em dưới 16 tuổi. Nếu chúng tôi biết rằng đã thu thập dữ liệu cá nhân của trẻ em mà không có sự đồng ý có thể xác minh từ cha mẹ, chúng tôi sẽ xóa dữ liệu đó.",
      ],
    },
  },
  {
    heading: { en: "10. Changes to This Policy", vi: "10. Thay đổi chính sách" },
    body: {
      en: [
        "We may update this Privacy Policy to reflect changes in the Service, our data practices, or the law. Material changes will be announced through the app or by email at least 14 days before they take effect. Continued use of the Service after the effective date constitutes acceptance of the revised Policy.",
      ],
      vi: [
        "Chúng tôi có thể cập nhật Chính sách Bảo mật này để phản ánh thay đổi trong Dịch vụ, thực hành dữ liệu của chúng tôi hoặc pháp luật. Các thay đổi quan trọng sẽ được thông báo qua ứng dụng hoặc email ít nhất 14 ngày trước khi có hiệu lực. Việc tiếp tục sử dụng Dịch vụ sau ngày có hiệu lực được xem là chấp nhận Chính sách đã sửa đổi.",
      ],
    },
  },
  {
    heading: { en: "11. Contact", vi: "11. Liên hệ" },
    body: {
      en: [
        "Privacy questions, deletion requests, and data-access requests can be sent to support@confluex.app. Please include the email associated with your account so we can verify your identity.",
      ],
      vi: [
        "Câu hỏi về quyền riêng tư, yêu cầu xóa dữ liệu và yêu cầu truy cập dữ liệu có thể gửi đến support@confluex.app. Vui lòng kèm email gắn với tài khoản của bạn để chúng tôi xác minh danh tính.",
      ],
    },
  },
];

const UI = {
  en: {
    title: "Privacy Policy",
    toggle: "Tiếng Việt",
    backToSignup: "Back to sign up",
  },
  vi: {
    title: "Chính sách Bảo mật",
    toggle: "English",
    backToSignup: "Quay lại đăng ký",
  },
} as const;

export default function PrivacyPage() {
  const [lang, setLang] = useState<Lang>("en");
  const t = UI[lang];

  return (
    <main className="h-screen overflow-y-auto bg-background font-ui text-on-surface custom-scrollbar">
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
