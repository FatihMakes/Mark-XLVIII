import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
    _PYGAME_OK = True
except ImportError:
    pygame = None
    _PYGAME_OK = False


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
CACHE_DIR = BASE_DIR / "cache" / "music"

SEARCH_URL = "http://search.kuwo.cn/r.s"
PLAY_URL = "http://api.xiaodaokg.com/kuwo.php"
LYRIC_URL = "http://m.kuwo.cn/newh5/singles/songinfoandlrc"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "Referer": "https://y.kuwo.cn/",
    "Cookie": "",
}


def _log(message: str, player=None) -> None:
    print(f"[Music] {message}")
    if player:
        try:
            player.write_log(f"Music: {message}")
        except Exception:
            pass


def _format_time(seconds: float | int | None) -> str:
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_quoted_value(text: str, key: str) -> str:
    marker = f'"{key}":"'
    start = text.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = text.find('"', start)
    if end == -1:
        return ""
    return text[start:end]


def _sanitize_filename(value: str) -> str:
    value = re.sub(r"[^\w\-.]+", "_", value.strip(), flags=re.UNICODE)
    value = value.strip("._")
    return value[:80] or "song"


class MusicPlayer:
    def __init__(self):
        self.current_song = ""
        self.current_url = ""
        self.song_id = ""
        self.total_duration = 0

        self.is_playing = False
        self.paused = False
        self.current_position = 0.0
        self.start_play_time = 0.0

        self.lyrics: list[tuple[float, str]] = []
        self.current_lyric_index = -1

        self.progress_thread: threading.Thread | None = None
        self.stop_progress = threading.Event()
        self.current_temp_file: Path | None = None

        self._lock = threading.RLock()
        self._mixer_ready = False
        self._last_search_result: dict[str, Any] | None = None

        self._ensure_cache_dir()
        self._clear_temp_cache()
        self._cleanup_temp_files()

    def _ensure_mixer(self) -> tuple[bool, str | None]:
        if not _PYGAME_OK:
            return False, "pygame 未安装，无法播放音乐。请安装 pygame。"
        if self._mixer_ready:
            return True, None
        try:
            pygame.mixer.init(frequency=24000, channels=1)
            self._mixer_ready = True
            return True, None
        except Exception as e:
            return False, f"初始化音乐播放失败: {e}"

    def _ensure_cache_dir(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "temp").mkdir(parents=True, exist_ok=True)

    def _clear_temp_cache(self) -> None:
        temp_dir = CACHE_DIR / "temp"
        if not temp_dir.exists():
            return
        for path in temp_dir.iterdir():
            if path.suffix in {".mp3", ".tmp", ".temp"}:
                try:
                    path.unlink()
                except Exception:
                    pass

    def _cleanup_temp_files(self, max_keep: int = 1) -> None:
        temp_dir = CACHE_DIR / "temp"
        if not temp_dir.exists():
            return
        files = []
        for path in temp_dir.iterdir():
            if path.name.startswith("playing_") and path.suffix == ".mp3":
                try:
                    files.append((path, path.stat().st_mtime))
                except Exception:
                    pass
        files.sort(key=lambda item: item[1], reverse=True)
        for path, _ in files[max_keep:]:
            if path != self.current_temp_file:
                try:
                    path.unlink()
                except Exception:
                    pass

    def _get_cache_path(self, song_id: str) -> Path:
        return CACHE_DIR / f"{_sanitize_filename(song_id)}.mp3"

    def search_song(self, song_name: str) -> dict[str, Any]:
        song_name = (song_name or "").strip()
        if not song_name:
            return {"status": "error", "message": "请提供歌曲或音乐关键字。"}

        with self._lock:
            self.current_song = song_name
            self.current_url = ""
            self.song_id = ""
            self.total_duration = 0
            self.lyrics = []
            self.current_lyric_index = -1

        try:
            song_id, url = self._get_song_info(song_name)
            if not song_id or not url:
                return {"status": "error", "message": f"未找到歌曲 '{song_name}' 或无法获取播放链接。"}

            with self._lock:
                self.current_url = url
                self.song_id = song_id
                self._last_search_result = {
                    "song_id": song_id,
                    "url": url,
                    "song": self.current_song,
                    "duration": self.total_duration,
                    "lyrics_count": len(self.lyrics),
                }

            return {
                "status": "success",
                "message": f"已找到歌曲: {self.current_song}",
                "song_id": song_id,
                "url": url,
                "duration": self.total_duration,
                "lyrics_count": len(self.lyrics),
            }
        except Exception as e:
            return {"status": "error", "message": f"搜索歌曲失败: {e}"}

    def _get_song_info(self, song_name: str) -> tuple[str, str]:
        search_params = {
            "all": song_name,
            "ft": "music",
            "newsearch": "1",
            "alflac": "1",
            "itemset": "web_2013",
            "client": "kt",
            "cluster": "0",
            "pn": "0",
            "rn": "1",
            "vermerge": "1",
            "rformat": "json",
            "encoding": "utf8",
            "show_copyright_off": "1",
            "pcmp4": "1",
            "ver": "mbox",
            "vipver": "MUSIC_8.7.6.0.BCS31",
            "plat": "pc",
            "devid": "0",
        }

        try:
            response = requests.get(SEARCH_URL, params=search_params, headers=HEADERS, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"[Music] search request failed: {e}")
            return "", ""

        response_text = response.text.replace("'", '"')
        song_id = _extract_quoted_value(response_text, "DC_TARGETID")
        if not song_id:
            return "", ""

        duration_text = _extract_quoted_value(response_text, "DURATION")
        duration = _safe_int(duration_text)
        artist = _extract_quoted_value(response_text, "ARTIST")
        title = _extract_quoted_value(response_text, "NAME") or song_name
        album = _extract_quoted_value(response_text, "ALBUM")

        display_name = title
        if artist:
            display_name = f"{title} - {artist}"
            if album:
                display_name += f" ({album})"

        with self._lock:
            self.current_song = display_name
            self.total_duration = duration

        play_api_url = f"{PLAY_URL}?ID={song_id}"
        for attempt in range(3):
            try:
                url_response = requests.get(play_api_url, headers=HEADERS, timeout=10)
                url_response.raise_for_status()
                play_url_text = url_response.text.strip()
                if play_url_text.startswith("http"):
                    self._fetch_lyrics(song_id)
                    return song_id, play_url_text
                print(f"[Music] invalid play URL response: {play_url_text[:100]}")
            except Exception as e:
                print(f"[Music] play URL request failed ({attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(1)

        return song_id, ""

    def _fetch_lyrics(self, song_id: str) -> None:
        try:
            response = requests.get(f"{LYRIC_URL}?musicId={song_id}", headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[Music] lyric request failed: {e}")
            return

        if not (data.get("status") == 200 and data.get("data") and data["data"].get("lrclist")):
            return

        lyrics = []
        for item in data["data"].get("lrclist", []):
            try:
                time_sec = float(item.get("time", "0"))
            except (TypeError, ValueError):
                time_sec = 0.0
            text = (item.get("lineLyric") or "").strip()
            if text and not text.startswith(("作词", "作曲", "编曲")):
                lyrics.append((time_sec, text))

        with self._lock:
            self.lyrics = lyrics

    def _download_file(self, url: str, file_path: Path) -> bool:
        headers = HEADERS.copy()
        headers.update({"Accept-Encoding": "gzip, deflate, br", "Referer": "https://music.163.com/"})
        temp_path = file_path.with_name(f"{file_path.name}.{int(time.time())}.tmp")

        try:
            with requests.get(url, stream=True, headers=headers, timeout=30) as response:
                response.raise_for_status()
                total_size = _safe_int(response.headers.get("content-length"))
                downloaded = 0
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=32768):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

            if downloaded <= 0 or (total_size > 0 and downloaded != total_size):
                temp_path.unlink(missing_ok=True)
                return False

            if file_path.exists():
                file_path.unlink(missing_ok=True)
            os.replace(temp_path, file_path)
            return True
        except Exception as e:
            print(f"[Music] download failed: {e}")
            temp_path.unlink(missing_ok=True)
            return False

    def search_play(self, song_name: str, choice: int = 1) -> dict[str, Any]:
        if song_name:
            result = self.search_song(song_name)
            if result.get("status") != "success":
                return result
        elif not self.current_url:
            return {"status": "error", "message": "请先提供歌曲关键字或搜索歌曲。"}

        if choice != 1:
            print("[Music] Kuwo reference search returns one final selected song; choice is accepted but ignored.")

        if self._play_url(self.current_url):
            return {
                "status": "success",
                "message": f"正在播放: {self.current_song}",
                "duration": self.total_duration,
            }
        return {"status": "error", "message": f"播放失败: {self.current_song}"}

    def _play_url(self, url: str) -> bool:
        ok, error = self._ensure_mixer()
        if not ok:
            print(f"[Music] {error}")
            return False

        with self._lock:
            if self.is_playing:
                self.stop()

            temp_dir = CACHE_DIR / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / "current_playing.mp3"
            cache_path = self._get_cache_path(self.song_id) if self.song_id else None

            try:
                use_path = None
                if cache_path and cache_path.exists():
                    try:
                        pygame.mixer.music.load(str(cache_path))
                        use_path = cache_path
                    except Exception as e:
                        print(f"[Music] cached file load failed, redownloading: {e}")
                        use_path = None

                if use_path is None:
                    if temp_file.exists():
                        try:
                            temp_file.unlink()
                        except Exception:
                            temp_file = temp_dir / f"playing_{int(time.time())}.mp3"
                    self.current_temp_file = temp_file
                    self._cleanup_temp_files(max_keep=3)

                    if cache_path and not cache_path.exists():
                        if not self._download_file(url, cache_path):
                            return False
                        use_path = cache_path
                    else:
                        if not self._download_file(url, temp_file):
                            return False
                        use_path = temp_file

                    pygame.mixer.music.load(str(use_path))

                pygame.mixer.music.play()
                self.is_playing = True
                self.paused = False
                self.current_position = 0.0
                self.start_play_time = time.time()
                self._start_progress_thread()
                return True
            except Exception as e:
                print(f"[Music] play failed: {e}")
                self.is_playing = False
                return False

    def play_pause(self) -> dict[str, Any]:
        if not self.is_playing:
            return self.play()
        if self.paused:
            return self.play()
        return self.pause()

    def play(self) -> dict[str, Any]:
        ok, error = self._ensure_mixer()
        if not ok:
            return {"status": "error", "message": error}

        with self._lock:
            if not self.is_playing:
                if self.current_url and self._play_url(self.current_url):
                    return {"status": "success", "message": f"开始播放: {self.current_song}"}
                return {"status": "error", "message": "没有可播放的歌曲。"}

            if self.paused:
                pygame.mixer.music.unpause()
                self.paused = False
                self.start_play_time = time.time() - self.current_position
                return {"status": "success", "message": f"继续播放: {self.current_song}"}

            return {"status": "info", "message": f"音乐已经在播放中: {self.current_song}"}

    def pause(self) -> dict[str, Any]:
        ok, error = self._ensure_mixer()
        if not ok:
            return {"status": "error", "message": error}

        with self._lock:
            if not self.is_playing:
                return {"status": "info", "message": "没有正在播放的歌曲。"}
            if self.paused:
                return {"status": "success", "message": f"音乐已暂停: {self.current_song}"}
            pygame.mixer.music.pause()
            self.paused = True
            self.current_position = time.time() - self.start_play_time
            return {
                "status": "success",
                "message": f"已暂停: {self.current_song} [{_format_time(self.current_position)}/{_format_time(self.total_duration)}]",
                "position": self.current_position,
            }

    def stop(self) -> dict[str, Any]:
        ok, error = self._ensure_mixer()
        if not ok:
            return {"status": "error", "message": error}

        with self._lock:
            if not self.is_playing:
                return {"status": "info", "message": "没有正在播放的歌曲。"}

            self.stop_progress.set()
            if self.progress_thread and self.progress_thread.is_alive():
                self.progress_thread.join(timeout=1.0)
            self.stop_progress.clear()

            pygame.mixer.music.stop()
            current_song = self.current_song
            self.is_playing = False
            self.paused = False
            self.current_position = 0.0
            self.current_temp_file = None
            self._cleanup_temp_files(max_keep=1)
            return {"status": "success", "message": f"已停止播放: {current_song}"}

    def seek(self, position: float) -> dict[str, Any]:
        ok, error = self._ensure_mixer()
        if not ok:
            return {"status": "error", "message": error}

        with self._lock:
            if not self.is_playing:
                return {"status": "error", "message": "没有正在播放的歌曲。"}

            position = max(0.0, min(float(position or 0), float(self.total_duration or 0)))
            self.current_position = position
            self.start_play_time = time.time() - position

            try:
                pygame.mixer.music.rewind()
                pygame.mixer.music.set_pos(position)
                if self.paused:
                    pygame.mixer.music.pause()
            except Exception as e:
                return {"status": "error", "message": f"跳转失败: {e}"}

            return {
                "status": "success",
                "message": f"已跳转到: {_format_time(position)}/{_format_time(self.total_duration)}",
                "position": position,
            }

    def get_lyrics_text(self) -> dict[str, Any]:
        with self._lock:
            if not self.lyrics:
                return {"status": "info", "message": "当前歌曲没有歌词。", "lyrics": []}
            lyrics = [f"[{_format_time(time_sec)}] {text}" for time_sec, text in self.lyrics]
        return {"status": "success", "message": f"获取到 {len(lyrics)} 行歌词。", "lyrics": lyrics}

    def status(self) -> dict[str, Any]:
        with self._lock:
            if not self.current_song:
                return {"status": "info", "message": "当前没有音乐。", "playing": False}
            position = self._get_current_position()
            state = "paused" if self.paused else "playing" if self.is_playing else "stopped"
            return {
                "status": "success",
                "message": f"{self.current_song} - {state} [{_format_time(position)}/{_format_time(self.total_duration)}]",
                "song": self.current_song,
                "song_id": self.song_id,
                "playing": self.is_playing,
                "paused": self.paused,
                "position": position,
                "duration": self.total_duration,
                "progress": self._get_progress(),
                "lyrics_count": len(self.lyrics),
            }

    def _get_current_position(self) -> float:
        if not self.is_playing or self.paused:
            return self.current_position
        if self.total_duration > 0:
            return min(float(self.total_duration), time.time() - self.start_play_time)
        return max(0.0, time.time() - self.start_play_time)

    def _get_progress(self) -> float:
        if self.total_duration <= 0:
            return 0.0
        return round(self._get_current_position() * 100 / self.total_duration, 1)

    def _start_progress_thread(self) -> None:
        if self.progress_thread and self.progress_thread.is_alive():
            self.stop_progress.set()
            self.progress_thread.join(timeout=1.0)
            self.stop_progress.clear()

        self.progress_thread = threading.Thread(target=self._update_progress_thread, daemon=True)
        self.progress_thread.start()

    def _update_progress_thread(self) -> None:
        while not self.stop_progress.is_set() and self.is_playing:
            if self.paused:
                time.sleep(0.2)
                continue

            self.current_position = time.time() - self.start_play_time
            if self.total_duration > 0 and self.current_position >= self.total_duration:
                self.current_position = float(self.total_duration)
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
                self.is_playing = False
                self.paused = False
                _log(f"播放完成: {self.current_song}")
                break

            time.sleep(0.1)


_PLAYER = MusicPlayer()


def _choice(parameters: dict[str, Any]) -> int:
    return max(1, _safe_int(parameters.get("choice"), 1))


def music_player(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "search_play").lower().strip()
    query = (params.get("query") or params.get("keyword") or params.get("song_name") or "").strip()

    try:
        if action in {"search", "find"}:
            result = _PLAYER.search_song(query)
            message = result.get("message", "搜索完成。")
            if result.get("status") == "success":
                message += f" 时长 {_format_time(result.get('duration'))}，歌词 {result.get('lyrics_count', 0)} 行。"
        elif action in {"search_play", "play_search", "play_song"}:
            result = _PLAYER.search_play(query, choice=_choice(params))
            message = result.get("message", "音乐已处理。")
        elif action == "play":
            if query:
                result = _PLAYER.search_play(query, choice=_choice(params))
            else:
                result = _PLAYER.play()
            message = result.get("message", "音乐已播放。")
        elif action == "pause":
            result = _PLAYER.pause()
            message = result.get("message", "音乐已暂停。")
        elif action in {"resume", "continue"}:
            result = _PLAYER.play()
            message = result.get("message", "音乐已继续。")
        elif action in {"toggle", "play_pause"}:
            result = _PLAYER.play_pause()
            message = result.get("message", "播放状态已切换。")
        elif action == "stop":
            result = _PLAYER.stop()
            message = result.get("message", "音乐已停止。")
        elif action == "seek":
            position = params.get("position_seconds", params.get("seconds", 0))
            result = _PLAYER.seek(float(position or 0))
            message = result.get("message", "已跳转。")
        elif action in {"lyrics", "get_lyrics"}:
            result = _PLAYER.get_lyrics_text()
            lyrics = result.get("lyrics") or []
            message = result.get("message", "当前歌曲没有歌词。")
            if lyrics:
                message += "\n" + "\n".join(lyrics[:80])
        elif action == "status":
            result = _PLAYER.status()
            message = result.get("message", "当前没有音乐。")
        else:
            message = "未知音乐操作。可用操作: search, search_play, play, pause, resume, toggle, stop, seek, lyrics, status。"

        _log(message, player)
        return message
    except Exception as e:
        message = f"音乐工具执行失败: {e}"
        _log(message, player)
        return message


def get_music_player() -> MusicPlayer:
    return _PLAYER
