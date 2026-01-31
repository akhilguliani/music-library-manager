"""VirtualDJ database XML parser and writer using lxml."""

from pathlib import Path
from typing import Optional, Iterator
from lxml import etree

from .models import Song, Tags, Infos, Scan, Poi, PoiType, Link, Playlist, DatabaseStats
from ..config import AUDIO_EXTENSIONS, NON_AUDIO_EXTENSIONS


class VDJDatabase:
    """Parser and writer for VirtualDJ database.xml files."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._tree: Optional[etree._ElementTree] = None
        self._root: Optional[etree._Element] = None
        self._songs: dict[str, Song] = {}
        self._playlists: list[Playlist] = []

    @property
    def is_loaded(self) -> bool:
        """Check if database is loaded."""
        return self._root is not None

    def load(self) -> None:
        """Load and parse the database XML file."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
        self._tree = etree.parse(str(self.db_path), parser)
        self._root = self._tree.getroot()

        # Parse all songs
        self._songs.clear()
        for song_elem in self._root.iter("Song"):
            song = self._parse_song(song_elem)
            if song:
                self._songs[song.file_path] = song

        # Parse playlists
        self._playlists.clear()
        for mylist in self._root.iter("MyList"):
            playlist = self._parse_playlist(mylist)
            if playlist:
                self._playlists.append(playlist)

    def _parse_song(self, elem: etree._Element) -> Optional[Song]:
        """Parse a Song element into a Song model."""
        file_path = elem.get("FilePath")
        if not file_path:
            return None

        file_size = elem.get("FileSize")

        # Parse Tags
        tags = None
        tags_elem = elem.find("Tags")
        if tags_elem is not None:
            tags = Tags(
                Author=tags_elem.get("Author"),
                Title=tags_elem.get("Title"),
                Genre=tags_elem.get("Genre"),
                Album=tags_elem.get("Album"),
                TrackNumber=self._safe_int(tags_elem.get("TrackNumber")),
                Year=self._safe_int(tags_elem.get("Year")),
                Composer=tags_elem.get("Composer"),
                Grouping=tags_elem.get("Grouping"),
                Remix=tags_elem.get("Remix"),
                Label=tags_elem.get("Label"),
                Comment=tags_elem.get("Comment"),
                Bpm=self._safe_float(tags_elem.get("Bpm")),
                Key=tags_elem.get("Key"),
                Color=tags_elem.get("Color"),
                Rating=self._safe_int(tags_elem.get("Rating")),
                Flag=self._safe_int(tags_elem.get("Flag")),
            )

        # Parse Infos
        infos = None
        infos_elem = elem.find("Infos")
        if infos_elem is not None:
            infos = Infos(
                SongLength=self._safe_float(infos_elem.get("SongLength")),
                FirstSeen=self._safe_int(infos_elem.get("FirstSeen")),
                LastPlay=self._safe_int(infos_elem.get("LastPlay")),
                PlayCount=self._safe_int(infos_elem.get("PlayCount")),
                Bitrate=self._safe_int(infos_elem.get("Bitrate")),
                Cover=infos_elem.get("Cover"),
            )

        # Parse Scan
        scan = None
        scan_elem = elem.find("Scan")
        if scan_elem is not None:
            scan = Scan(
                Bpm=self._safe_float(scan_elem.get("Bpm")),
                Key=scan_elem.get("Key"),
                Volume=self._safe_float(scan_elem.get("Volume")),
                Flag=self._safe_int(scan_elem.get("Flag")),
            )

        # Parse Poi (cue points, beatgrid, loops)
        pois = []
        for poi_elem in elem.iter("Poi"):
            poi_type_str = poi_elem.get("Type")
            if poi_type_str:
                try:
                    poi_type = PoiType(poi_type_str)
                    poi = Poi(
                        Type=poi_type,
                        Pos=self._safe_float(poi_elem.get("Pos")) or 0.0,
                        Name=poi_elem.get("Name"),
                        Num=self._safe_int(poi_elem.get("Num")),
                        Size=self._safe_float(poi_elem.get("Size")),
                        Point=self._safe_float(poi_elem.get("Point")),
                        Bpm=self._safe_float(poi_elem.get("Bpm")),
                    )
                    pois.append(poi)
                except ValueError:
                    pass  # Unknown POI type

        # Parse Links
        links = []
        for link_elem in elem.iter("Link"):
            source = link_elem.get("Source")
            if source:
                links.append(Link(Source=source))

        return Song(
            FilePath=file_path,
            FileSize=self._safe_int(file_size),
            tags=tags,
            infos=infos,
            scan=scan,
            pois=pois,
            links=links,
        )

    def _parse_playlist(self, elem: etree._Element) -> Optional[Playlist]:
        """Parse a MyList element into a Playlist model."""
        name = elem.get("Name")
        if not name:
            return None

        file_paths = []
        for song_elem in elem.iter("Song"):
            file_path = song_elem.get("FilePath")
            if file_path:
                file_paths.append(file_path)

        return Playlist(Name=name, file_paths=file_paths)

    @staticmethod
    def _safe_int(value: Optional[str]) -> Optional[int]:
        """Safely convert string to int."""
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: Optional[str]) -> Optional[float]:
        """Safely convert string to float."""
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @property
    def songs(self) -> dict[str, Song]:
        """Return all songs keyed by file path."""
        return self._songs

    @property
    def playlists(self) -> list[Playlist]:
        """Return all playlists."""
        return self._playlists

    def get_song(self, file_path: str) -> Optional[Song]:
        """Get a song by file path."""
        return self._songs.get(file_path)

    def iter_songs(self) -> Iterator[Song]:
        """Iterate over all songs."""
        yield from self._songs.values()

    def get_stats(self, check_existence: bool = False) -> DatabaseStats:
        """Calculate database statistics."""
        stats = DatabaseStats(total_songs=len(self._songs))

        for song in self._songs.values():
            # Check path type
            if song.is_netsearch:
                stats.netsearch += 1
            elif song.is_windows_path:
                stats.windows_paths += 1
                drive = song.file_path[0].upper()
                if drive == "C":
                    stats.windows_c_paths += 1
                elif drive == "D":
                    stats.windows_d_paths += 1
                elif drive == "E":
                    stats.windows_e_paths += 1
            else:
                stats.local_files += 1
                if song.file_path.startswith("/Users/"):
                    stats.mac_home_paths += 1
                elif song.file_path.startswith("/Volumes/MyNVMe"):
                    stats.mynvme_paths += 1

            # Check file type
            ext = song.extension
            if ext in AUDIO_EXTENSIONS:
                stats.audio_files += 1
            elif ext in NON_AUDIO_EXTENSIONS or ext not in AUDIO_EXTENSIONS:
                if not song.is_netsearch:
                    stats.non_audio_files += 1

            # Check metadata
            if song.energy is not None:
                stats.with_energy += 1
            if song.cue_points:
                stats.with_cue_points += 1

            # Check file existence (expensive)
            if check_existence and not song.is_windows_path and not song.is_netsearch:
                if not Path(song.file_path).exists():
                    stats.missing_files += 1

        return stats

    def update_song_tags(self, file_path: str, **kwargs) -> bool:
        """Update tags for a song in the XML tree."""
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        # Find the song element
        for song_elem in self._root.iter("Song"):
            if song_elem.get("FilePath") == file_path:
                tags_elem = song_elem.find("Tags")
                if tags_elem is None:
                    tags_elem = etree.SubElement(song_elem, "Tags")

                for key, value in kwargs.items():
                    if value is not None:
                        tags_elem.set(key, str(value))
                    elif key in tags_elem.attrib:
                        del tags_elem.attrib[key]

                # Update in-memory model
                if file_path in self._songs:
                    song = self._songs[file_path]
                    if song.tags is None:
                        song.tags = Tags()
                    for key, value in kwargs.items():
                        if hasattr(song.tags, key.lower()):
                            setattr(song.tags, key.lower(), value)

                return True
        return False

    def update_song_scan(self, file_path: str, **kwargs) -> bool:
        """Update scan data for a song in the XML tree."""
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        for song_elem in self._root.iter("Song"):
            if song_elem.get("FilePath") == file_path:
                scan_elem = song_elem.find("Scan")
                if scan_elem is None:
                    scan_elem = etree.SubElement(song_elem, "Scan")

                for key, value in kwargs.items():
                    if value is not None:
                        scan_elem.set(key, str(value))

                return True
        return False

    def remap_path(self, old_path: str, new_path: str) -> bool:
        """Remap a file path in the database."""
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        for song_elem in self._root.iter("Song"):
            if song_elem.get("FilePath") == old_path:
                song_elem.set("FilePath", new_path)

                # Update in-memory model
                if old_path in self._songs:
                    song = self._songs.pop(old_path)
                    song.file_path = new_path
                    self._songs[new_path] = song

                return True
        return False

    def remove_song(self, file_path: str) -> bool:
        """Remove a song from the database."""
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        for song_elem in self._root.iter("Song"):
            if song_elem.get("FilePath") == file_path:
                parent = song_elem.getparent()
                if parent is not None:
                    parent.remove(song_elem)
                    self._songs.pop(file_path, None)
                    return True
        return False

    def add_song(self, file_path: str, file_size: Optional[int] = None) -> etree._Element:
        """Add a new song to the database."""
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        song_elem = etree.SubElement(self._root, "Song")
        song_elem.set("FilePath", file_path)
        if file_size is not None:
            song_elem.set("FileSize", str(file_size))

        # Add to in-memory model
        song = Song(FilePath=file_path, FileSize=file_size)
        self._songs[file_path] = song

        return song_elem

    def save(self, output_path: Optional[Path] = None) -> None:
        """Save the database to file.

        This method preserves VDJ's expected format:
        - Double quotes in XML declaration
        - Windows line endings (CRLF)
        """
        if not self.is_loaded:
            raise RuntimeError("Database not loaded")

        path = output_path or self.db_path

        # Serialize the XML tree
        xml_bytes = etree.tostring(
            self._root,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=False,
        )

        # lxml uses single quotes in XML declaration - VDJ expects double quotes
        # Also ensure we use CRLF line endings which VDJ expects
        xml_str = xml_bytes.decode("UTF-8")

        # Fix XML declaration quotes: <?xml version='1.0' -> <?xml version="1.0"
        if xml_str.startswith("<?xml"):
            # Replace single quotes with double quotes in the declaration
            decl_end = xml_str.index("?>") + 2
            declaration = xml_str[:decl_end]
            declaration = declaration.replace("'", '"')
            xml_str = declaration + xml_str[decl_end:]

        # Convert to CRLF line endings (Windows style) that VDJ expects
        xml_str = xml_str.replace("\r\n", "\n").replace("\n", "\r\n")

        # Write as binary to preserve exact bytes
        with open(path, "wb") as f:
            f.write(xml_str.encode("UTF-8"))

    def merge_from(self, other: "VDJDatabase", prefer_other: bool = True) -> dict:
        """Merge songs from another database into this one.

        Args:
            other: Another VDJDatabase to merge from
            prefer_other: If True, prefer metadata from other database on conflicts

        Returns:
            Dict with merge statistics
        """
        if not self.is_loaded or not other.is_loaded:
            raise RuntimeError("Both databases must be loaded")

        stats = {"added": 0, "updated": 0, "skipped": 0}

        for file_path, other_song in other.songs.items():
            if file_path in self._songs:
                if prefer_other:
                    # Update existing song with richer metadata from other
                    existing = self._songs[file_path]
                    updated = False

                    # Update tags if other has more info
                    if other_song.tags:
                        if not existing.tags or (other_song.energy and not existing.energy):
                            self.update_song_tags(
                                file_path,
                                Grouping=other_song.tags.grouping,
                                Comment=other_song.tags.comment,
                            )
                            updated = True

                    # Update scan if other has BPM/key
                    if other_song.scan and other_song.scan.bpm:
                        if not existing.scan or not existing.scan.bpm:
                            self.update_song_scan(
                                file_path,
                                Bpm=other_song.scan.bpm,
                                Key=other_song.scan.key,
                            )
                            updated = True

                    if updated:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # Add new song (copy XML element)
                for song_elem in other._root.iter("Song"):
                    if song_elem.get("FilePath") == file_path:
                        # Deep copy the element
                        new_elem = etree.fromstring(etree.tostring(song_elem))
                        self._root.append(new_elem)
                        self._songs[file_path] = other_song
                        stats["added"] += 1
                        break

        return stats
