import React, { useEffect, useRef, useState } from 'react';
import { RotateCcw, SkipBack, SkipForward, Volume2 } from 'lucide-react';

interface AudioPlayerProps {
  src: string;
}

export function AudioPlayer({ src }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);

  useEffect(() => {
    if (!audioRef.current) return;
    audioRef.current.volume = volume;
    audioRef.current.playbackRate = playbackRate;
  }, [volume, playbackRate]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    audio.pause();
    audio.currentTime = 0;
    audio.load();

    const syncDuration = () => {
      if (isFinite(audio.duration) && audio.duration > 0) {
        setDuration(audio.duration);
      }
    };

    syncDuration();
    const timeoutId = window.setTimeout(syncDuration, 300);
    return () => window.clearTimeout(timeoutId);
  }, [src]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) audioRef.current.pause();
    else audioRef.current.play();
    setIsPlaying(!isPlaying);
  };

  const togglePlayRef = useRef(togglePlay);
  useEffect(() => {
    togglePlayRef.current = togglePlay;
  }, [togglePlay]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.code === 'Space') {
        e.preventDefault();
        togglePlayRef.current();
      }
    };
    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, []);

  const skip = (amount: number) => {
    if (!audioRef.current) return;
    let next = audioRef.current.currentTime + amount;
    if (next < 0) next = 0;
    if (duration > 0 && next > duration) next = duration;
    audioRef.current.currentTime = next;
    setCurrentTime(next);
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);
    if (isFinite(audioRef.current.duration) && audioRef.current.duration > 0) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current && isFinite(audioRef.current.duration)) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (!audioRef.current) return;
    audioRef.current.currentTime = time;
    setCurrentTime(time);
  };

  const handleVolume = (e: React.ChangeEvent<HTMLInputElement>) => {
    setVolume(parseFloat(e.target.value));
  };

  const formatTime = (time: number) => {
    if (isNaN(time) || !isFinite(time)) return '0:00';
    const min = Math.floor(time / 60);
    const sec = Math.floor(time % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
  };

  const toggleSpeed = () => {
    const rates = [1, 1.25, 1.5, 1.75, 2, 2.5, 3];
    const idx = rates.indexOf(playbackRate);
    setPlaybackRate(rates[(idx + 1) % rates.length]);
  };

  return (
    <div
      className="flex w-full flex-col gap-2 px-0.5 py-2 sm:flex-row sm:items-center"
      style={{ background: 'transparent' }}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onLoadedData={handleLoadedMetadata}
        onCanPlay={handleLoadedMetadata}
        onDurationChange={e => {
          if (isFinite(e.currentTarget.duration)) setDuration(e.currentTarget.duration);
        }}
        onEnded={() => setIsPlaying(false)}
      />

      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          onClick={togglePlay}
          className="premium-button-secondary h-8 w-8 rounded-[10px] p-0"
          style={isPlaying ? { background: 'var(--accent-subtle)', borderColor: 'var(--border-strong)', color: 'var(--text-primary)' } : undefined}
          aria-label={isPlaying ? 'Metti in pausa' : 'Avvia riproduzione'}
        >
          {isPlaying ? (
            <span aria-hidden="true" className="text-[11px] font-semibold leading-none tracking-[-0.12em]">II</span>
          ) : (
            <span aria-hidden="true" className="translate-x-[1px] text-[13px] leading-none">▶</span>
          )}
        </button>
        <button type="button" onClick={() => skip(-10)} className="icon-button h-8 w-8 rounded-[10px]" aria-label="Indietro di 10 secondi">
          <SkipBack className="h-3.5 w-3.5" />
        </button>
        <button type="button" onClick={() => skip(10)} className="icon-button h-8 w-8 rounded-[10px]" aria-label="Avanti di 10 secondi">
          <SkipForward className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-center justify-end gap-3 pr-0.5 text-[11px] font-semibold tabular-nums" style={{ color: 'var(--text-muted)' }}>
          <span>{formatTime(currentTime)} / {formatTime(duration)}</span>
        </div>
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          className="custom-scrubber w-full"
          style={{ '--progress': duration ? `${(currentTime / duration) * 100}%` : '0%' } as React.CSSProperties}
        />
      </div>

      <div className="flex items-center gap-2 sm:ml-1">
        <button type="button" onClick={toggleSpeed} className="premium-button-secondary h-8 min-w-[46px] rounded-[10px] px-2 py-1 text-[12px]">
          {playbackRate}x
        </button>
        <div className="flex items-center gap-1.5">
          <Volume2 className="h-3.5 w-3.5" style={{ color: 'var(--text-muted)' }} />
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={handleVolume}
            className="custom-volume w-16"
            style={{ '--progress': `${volume * 100}%` } as React.CSSProperties}
          />
        </div>
        <button type="button" onClick={() => skip(-duration)} className="icon-button h-8 w-8 rounded-[10px]" aria-label="Torna all'inizio">
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
