import { UploadCloud } from 'lucide-react';

interface DropZoneProps {
  isDragging: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
  onClick: () => void;
}

export function DropZone({ isDragging, onDragOver, onDragLeave, onDrop, onClick }: DropZoneProps) {
  return (
    <div
      onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop} onClick={onClick}
      className={`dropzone-card relative cursor-pointer flex flex-col items-center justify-center py-12 px-6 text-center group${isDragging ? ' is-dragging' : ''}`}
    >
      <svg className="dz-border-svg" aria-hidden="true">
        <rect className="dz-border-rect" x="0" y="0" width="100%" height="100%" rx="24" ry="24" />
      </svg>
      <div className="w-14 h-14 mb-4 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform duration-300 shadow-xl" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
        <UploadCloud className="w-7 h-7" style={{ color: isDragging ? 'var(--accent-text)' : 'var(--text-muted)' }} />
      </div>
      <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--text-primary)' }}>Clicca per sfogliare i file</h3>
      <p className="text-sm max-w-sm" style={{ color: 'var(--text-muted)' }}>
        Supporta audio e video (.mp3, .m4a, .wav, .mp4, .mkv, .webm, .ogg, .flac, .aac).<br/>Coda illimitata - elaborazione sequenziale.
      </p>
    </div>
  );
}
