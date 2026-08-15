import { useTranslation } from "react-i18next";
import { toast } from "@/components/ui/Toast";
import { openUrl } from "@/services/tauri";
import { copyText } from "@/utils";

function GithubIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

export function AboutSection() {
  const { t } = useTranslation();

  return (
    <div className="settings-about">
      <section className="settings-about-section">
        <h4>{t("about.sourceLicenseTitle", "开源协议")}</h4>
        <p>
          <GithubIcon />
          <button
            type="button"
            className="settings-about-link"
            onClick={() =>
              void openUrl(
                "https://github.com/mrtanweijie/ai-divine-desktop"
              )
            }
          >
            github.com/mrtanweijie/ai-divine-desktop
          </button>
        </p>
        <p>
          {t("about.licenseText", "本项目采用 MIT License。")}
          <button
            type="button"
            className="settings-about-link"
            onClick={() =>
              void openUrl(
                "https://github.com/mrtanweijie/ai-divine-desktop/blob/main/LICENSE"
              )
            }
          >
            MIT License
          </button>
        </p>
      </section>
      <section className="settings-about-section">
        <h4>{t("about.disclaimerTitle", "免责声明")}</h4>
        <ul>
          <li>
            {t(
              "about.disclaimerAiContent",
              "AI 生成的内容仅供参考，可能包含错误、过时信息或偏差；重要信息请自行核实，涉及法律、医疗、财务等专业决策请咨询专业人士。"
            )}
          </li>
          <li>
            {t(
              "about.disclaimerRisk",
              "使用本软件处理重要文件或执行高风险操作前，请先备份数据并自行评估风险。"
            )}
          </li>
          <li>
            {t(
              "about.disclaimerAsIs",
              "本项目按“现状”提供，不承诺特定结果，也不保证运行无错误；因使用本软件造成的任何直接或间接损失，由使用者自行承担。"
            )}
          </li>
          <li>
            {t(
              "about.disclaimerThirdParty",
              "调用第三方模型服务时，费用、数据流转、隐私与服务可用性遵循对应服务商的规则。"
            )}
          </li>
          <li>
            {t(
              "about.disclaimerPrivacy",
              "对话、文件和设置默认保存在本机；调用模型服务时，必要的对话上下文会发送给对应服务商。"
            )}
          </li>
        </ul>
      </section>
      <section className="settings-about-section">
        <h4>{t("about.contactTitle", "联系方式")}</h4>
        <p>
          {t("about.contactText", "问题反馈或合作请联系：")}
          <button
            type="button"
            className="settings-about-link"
            onClick={() => {
              void copyText("tanweijie@outlook.com").then(() => {
                toast.success(t("common.copied", "已复制"));
              });
            }}
          >
            tanweijie@outlook.com
          </button>
        </p>
      </section>
    </div>
  );
}
