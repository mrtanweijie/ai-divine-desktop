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

export function ConfirmDialog({
  title,
  description,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  return (
    <Modal
      open
      title={title}
      onClose={onCancel}
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
