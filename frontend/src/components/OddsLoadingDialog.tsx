import { useEffect, useRef } from 'react';
import './odds-loading-dialog.css';

interface OddsLoadingDialogProps {
  label: string;
  completed: number;
  total: number;
  onCancel: () => void;
}

export function OddsLoadingDialog({ label, completed, total, onCancel }: OddsLoadingDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    cancelRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="odds-loading-dialog"
      aria-labelledby="odds-loading-title"
      aria-describedby="odds-loading-description"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <span className="eyebrow">Odds Fantasy</span>
      <h2 id="odds-loading-title">{label}</h2>
      <p id="odds-loading-description">
        Gathering odds and updating projections. Other controls are unavailable until this completes
        or you cancel.
      </p>
      <div
        className="odds-loading-track"
        role="progressbar"
        aria-label="Odds refresh progress"
        aria-valuetext={
          total ? `${completed} of ${total} sections ready` : 'Waiting for sportsbook data'
        }
      >
        <span className="odds-loading-indicator" />
      </div>
      <div className="odds-loading-footer">
        <span className="odds-loading-detail" role="status">
          {total ? `${completed} of ${total} sections ready` : 'Waiting for sportsbook response…'}
        </span>
        <button ref={cancelRef} type="button" className="odds-loading-cancel" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </dialog>
  );
}
