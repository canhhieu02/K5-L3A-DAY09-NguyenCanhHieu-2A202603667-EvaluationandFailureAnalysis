# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
Chạy: `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.800 ≥ 0.7) | **Dùng** |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (κ=0.375 < 0.6, R=0.300 < 0.7) | **Loại** |

---

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Đề xuất sửa rubric |
|---|---|---|---|---|---|
| 1 | **H-008** (`judge_tone`): *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* | PASS | FAIL | Người đúng | Ngôn từ xưng hô "em... anh rồi nha... check giúp em" quá suồng sã, thiếu chuẩn mực CSKH doanh nghiệp. Judge nhầm lẫn giữa thân thiện và suồng sã. **Sửa rubric:** Cấm đại từ xưng hô thân mật không quy chuẩn (`anh/em`, `nha`, từ lóng tiếng Anh như `check`). |
| 2 | **H-029** (`judge_tone`): *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* | PASS | FAIL | Người đúng | Giọng điệu cộc lốc, gắt gỏng và mang tính ra lệnh ("không cần nhắn thêm"). Judge chỉ bắt từ khóa lịch sự đầu câu ("Dạ, vui lòng"). **Sửa rubric:** Đánh giá ngữ điệu toàn câu, cấm các câu mang hàm ý từ chối giao tiếp hay gắt gỏng với khách. |
| 3 | **H-042** (`judge_tone`): *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* | FAIL | PASS | Người đúng (Judge quá khắt khe) | Câu trả lời ngắn gọn, lịch sự ("Dạ... ạ"), cung cấp đúng thông tin số tiền và thời gian tiền về. Judge phạt vì "thiếu lời xin lỗi". **Sửa rubric:** Với yêu cầu đã giải quyết thành công, không bắt buộc phải có câu xin lỗi lặp lại nếu thông tin đã đầy đủ và nhã nhặn. |
| 4 | **HL-015** (`judge_helpful`): *"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."* | PASS | FAIL | Người đúng | Văn bản reply nói hoàn 55.000đ nhưng thực tế ledger chỉ ghi nhận hoàn 40.000đ (FM-08 misreport). Judge chỉ đọc văn bản surface text nên thấy trôi chảy là cho PASS. **Sửa rubric:** Không dùng judge chay để chấm nghiệp vụ; tính hữu ích liên quan đến số tiền bắt buộc phải đối chiếu ledger bằng Code Grader. |
| 5 | **HL-016** (`judge_helpful`): *"Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn..."* | PASS | FAIL | Người đúng | Đây là câu xin lỗi suông (boilerplate apology) hoàn toàn không giải quyết khiếu nại (trong khi ledger thực tế đã duyệt hoàn 35.000đ nhưng không thông báo cho khách). Judge nhầm lẫn giữa lời xin lỗi lịch thiệp và giá trị giải quyết vấn đề. **Sửa rubric:** Tách bạch tiêu chí Tone và Helpfulness; phản hồi chỉ có lời xin lỗi mà không có thông tin xử lý thực tế phải bị đánh FAIL. |

---

## Kết luận

1. **Tiêu chí bị loại và lý do:**
   * **`helpful` bị loại hoàn toàn khỏi CI gate:**
     * Ma trận nhầm lẫn: `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}` trên $n=100$.
     * **Recall cực kỳ thấp ($R = 0.300 < 0.700$):** Bỏ lọt tới 21/30 trường hợp lỗi nghiêm trọng (chỉ phát hiện được 30% lỗi).
     * **Cohen's Kappa quá thấp ($\kappa = 0.375 < 0.600$):** Độ thống nhất giữa judge và con người sau khi loại bỏ yếu tố ngẫu nhiên là rất yếu.
     * Tỉ lệ lỗi quan sát thấy bởi judge chỉ là $9\%$, trong khi tỉ lệ lỗi thực tế sau khi hiệu chỉnh Rogan-Gladen là $30\%$. Nếu dùng judge này làm gate chặn release, hệ thống sẽ để lọt $70\%$ phản hồi sai/vô ích ra môi trường production.
   * **`tone_ok` được chấp thuận sử dụng:**
     * Ma trận nhầm lẫn: `{'tp': 24, 'fp': 4, 'fn': 6, 'tn': 66}`.
     * Đạt mọi ngưỡng sàn kiểm định: $\kappa = 0.757 \ge 0.600$, $P = 0.857 \ge 0.800$, $R = 0.800 \ge 0.700$.

2. **Rủi ro còn lại & Đề xuất:**
   * Judge hiện tại mới chỉ được hiệu chuẩn trên tập dữ liệu replay công khai có sẵn (`judge_tone_public.csv`).
   * Cần định kỳ thu thập mẫu phản hồi từ người dùng thực tế và dán nhãn độc lập (held-out test set) để liên tục kiểm chuẩn lại tính ổn định của LLM Judge, tránh hiện tượng data drift hoặc prompt overfitting.
   * Các yếu tố liên quan đến tiền bạc, trạng thái đơn hàng và quyền duyệt tuyệt đối không giao cho LLM Judge mà phải kiểm soát chặt chẽ bằng Code Evaluator.
