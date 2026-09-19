import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import "./index.less";

interface ConfirmDialogProps {
  title: string;
  description: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ title, description, onConfirm, onCancel }: ConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <Modal
      open
      title={title}
      onClose={onCancel}
      // 确认对话框不显示右上角 X：底部「取消 / 确认」才是预期操作入口，
      // 且 Esc / 点遮罩已经等于取消。多一个 X 反而容易让人随手关掉危险操作。
      showClose={false}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            {t("common.cancel", "取消")}
          </Button>
          <Button variant="danger" onClick={onConfirm}>
            {t("common.confirm", "确认")}
          </Button>
        </>
      }
    >
      <div className="confirm-content">
        <AlertTriangle size={18} />
        <p>{description}</p>
      </div>
    </Modal>
  );
}
