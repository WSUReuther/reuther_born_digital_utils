# Process legacy disk images (extract contents and run various reports on images and files)
# Heavily inspired by/adopted from Tessa Walsh's diskimageprocessor (https://github.com/CCA-Public/diskimageprocessor)
# Additional inspiration from Mike Shallcross (https://github.com/IUBLibTech/bdpl_ingest)

import argparse
import csv
import datetime
import os
import platform
import shutil
import subprocess
import sys
import time

import Objects


class DiskImageProcessor:
    def __init__(self, source_dir, source_image, image_path):
        self.source_dir = source_dir
        self.source_image = source_image
        self.image_path = image_path

        self.mount_and_copy_list = ["udf"]
        self.unhfs_list = ["osx", "hfs", "apple", "apple_hfs", "mfs", "hfs plus"]
        self.tsk_list = ["ntfs", "fat", "exfat", "ext", "iso9660", "hfs+", "ufs", "raw", "swap", "yaffs2"]

        self.premis_events = []

        self.setup_dirs()

    def setup_dirs(self):
        image_filename, image_ext = os.path.splitext(self.source_image)
        self.image_dir = os.path.join(self.source_dir, image_filename)
        self.objects_dir = os.path.join(self.image_dir, "objects")
        self.metadata_dir = os.path.join(self.image_dir, "metadata")
        self.subdoc_dir = os.path.join(self.metadata_dir, "submissionDocumentation")
        self.dfxml_file = os.path.join(self.subdoc_dir, "dfxml.xml")
        self.premis_csv = os.path.join(self.subdoc_dir, "premis.csv")
        self.brunnhilde_dir = os.path.join(self.subdoc_dir, "brunnhilde")
        for dirpath in [self.image_dir, self.objects_dir, self.metadata_dir, self.subdoc_dir]:
            os.makedirs(dirpath)

    def record_premis(self, timestamp, event_type, event_outcome, event_detail, event_detail_note, agent_info):
        premis_event = {}
        premis_event["eventType"] = event_type
        premis_event["eventOutcomeDetail"] = event_outcome
        premis_event["timestamp"] = timestamp
        premis_event["eventDetailInfo"] = event_detail
        premis_event["eventDetailInfo_additional"] = event_detail_note
        premis_event["linkingAgentIDvalue"] = agent_info

        self.premis_events.append(premis_event)

    def write_premis_csv(self):
        headers = ["eventType", "eventOutcomeDetail", "timestamp", "eventDetailInfo", "eventDetailInfo_additional", "linkingAgentIDvalue"]
        with open(self.premis_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(self.premis_events)

    def process_disk(self):
        status = ""
        message = ""
        self.run_preliminary_tools()
        potential_video = self.check_for_video()
        if potential_video:
            status = "skipped"
            message = "Image contains VIDEO_TS or AUDIO_TS directories"
            return status, message
        else:
            status, message = self.characterize_and_extract_files()
            if status == "skipped":
                return status, message
            else:
                self.run_brunnhilde()
                self.write_premis_csv()
                self.bag_item()
                status = "success"
                return status, message

    def run_preliminary_tools(self):
        self.disktype_txt = os.path.join(self.subdoc_dir, "disktype.txt")
        disktype_cmd = ["disktype", self.image_path]
        timestamp = str(datetime.datetime.now())
        with open(self.disktype_txt, "w") as f:
            disktype_result = subprocess.run(disktype_cmd, stdout=f)
        self.record_premis(
            timestamp,
            'forensic feature analysis',
            disktype_result.returncode,
            subprocess.list2cmdline(disktype_result.args),
            "Determined fisk image file system information",
            'disktype'
        )

    def check_for_video(self):
        potential_video = False
        for line in open(self.isoinfo_txt, "r"):
            if line.strip() in ["/AUDIO_TS", "/VIDEO_TS"]:
                potential_video = True
        return potential_video

    def characterize_and_extract_files(self):
        self.parse_disk_filesystems()

        if len(self.partition_info_list) <= 1:
            status, message = self.handle_file_extraction(self.objects_dir, False)
        else:
            for partition_info in self.partition_info_list:
                out_folder = os.path.join(self.objects_dir, f"partition_{partition_info['slot']}")
                status, message = self.handle_file_extraction(out_folder, partition_info)
        return status, message

    def parse_disk_filesystems(self):
        print("Parsing disk filesystems")
        self.partition_info_list = []
        self.filesystems = []
        with open(self.disktype_txt, "r") as f:
            dt_output = f.read()

        if "Partitions" in dt_output:
            partitions = dt_output.split("Partition ")[1:]
            if len(partitions) == 2 and "Apple_partition_map" in partitions[0]:
                handle_partitions = False
            elif len(partitions) > 1:
                handle_partitions = True
        else:
            handle_partitions = False

        if handle_partitions:
            mmls_version_cmd = ["mmls", "-V"]
            mmls_version = subprocess.run(mmls_version_cmd, capture_output=True).stdout.decode("utf-8").strip()
            mmls_output = os.path.join(self.subdoc_dir, "mmls_output.txt")
            mmls_cmd = ["mmls", self.image_path]
            timestamp = str(datetime.datetime.now())
            with open(mmls_output, "w") as f:
                mmls_result = subprocess.run(mmls_cmd, stdout=f)

            self.record_premis(
                timestamp,
                'forensic feature analysis',
                mmls_result.returncode,
                subprocess.list2cmdline(mmls_result.args),
                "Determined the layout of partitions",
                mmls_version
            )

            if os.stat(mmls_output).st_size > 0:
                with open(mmls_output, "r") as f:
                    mmls_info = [m.split("\n") for m in f.read().splitlines()[5:]]
                for mm in mmls_info:
                    partition_info = {}
                    for partition in partitions:
                        sector_length = mm[0].split()[4].lstrip('0')
                        sector_start = mm[0].split()[2]
                        if 'file system' in partition and f", {sector_length} sectors from {sector_start.lstrip('0')})" in partition:
                            filesystem_names = [d.split(' file system')[0].strip().lower() for d in partition.split('\n') if ' file system' in d]
                            partition_info["start"] = sector_start
                            partition_info["filesystems"] = filesystem_names
                            partition_info["slot"] = mm[0].split()[1]
                            self.partition_info_list.append(partition_info)
        else:
            dt_info = dt_output.splitlines()
            for dt in dt_info:
                if 'file system' in dt:
                    filesystem = dt.split(' file system')[0].strip().lower()
                    self.filesystems.append(filesystem)

    def handle_file_extraction(self, out_folder, partition):
        if partition:
            filesystems = partition["filesystems"]
        else:
            filesystems = self.filesystems

        if len(filesystems) == 1:
            filesystem = filesystems[0]
        elif len(filesystems) == 3 and sorted(filesystems) == ["hfs plus", "iso9660", "udf"]:
            # hybrid disk, use tsk
            filesystem = "iso9660"
        else:
            return "skipped", "Unable to identify filesystem"

        if filesystem in self.tsk_list:
            self.carve_files_tsk(out_folder, partition)
        elif filesystem in self.unhfs_list:
            self.carve_files_unhfs(out_folder, partition)
        elif filesystem in self.mount_and_copy_list:
            self.mount_and_copy_files(out_folder)
        else:
            return "skipped", "Filesystem not supported"

        return "success", ""

    def carve_files_tsk(self, out_folder, partition):
        self.generate_dfxml_fiwalk()

        print("Carving files using tsk_recover")
        tsk_version_cmd = ["tsk_recover", "-V"]
        tsk_version = subprocess.run(tsk_version_cmd, capture_output=True).stdout.decode("utf-8").strip()
        if partition:
            tsk_cmd = ["tsk_recover", "-a", "-o", partition["start"], self.image_path, out_folder]
        else:
            tsk_cmd = ["tsk_recover", "-a", self.image_path, out_folder]
        timestamp = str(datetime.datetime.now())
        tsk_result = subprocess.run(tsk_cmd)
        self.record_premis(
            timestamp,
            'replication',
            tsk_result.returncode,
            subprocess.list2cmdline(tsk_result.args),
            "Created a bit-wise identical copy of contents on disk image",
            f"tsk_recover: {tsk_version}"
        )

        self.fix_dates(out_folder)

    def fix_dates(self, out_folder):
        print("Fixing dates from DFXML")
        timestamp = str(datetime.datetime.now())
        try:
            for (event, obj) in Objects.iterparse(self.dfxml_file):
                # only work on FileObjects
                if not isinstance(obj, Objects.FileObject):
                    continue

                # skip directories and links
                if obj.name_type:
                    if obj.name_type not in ["r", "d"]:
                        continue

                # record filename
                dfxml_filename = obj.filename
                dfxml_filedate = int(time.time())  # default to current time

                # record last modified or last created date
                try:
                    mtime = obj.mtime
                    mtime = str(mtime)
                except:
                    pass

                try:
                    crtime = obj.crtime
                    crtime = str(crtime)
                except:
                    pass

                # fallback to created date if last modified doesn't exist
                if mtime and (mtime != "None"):
                    mtime = time_to_int(mtime[:19])
                    dfxml_filedate = mtime
                elif crtime and (crtime != "None"):
                    crtime = time_to_int(crtime[:19])
                    dfxml_filedate = crtime
                else:
                    continue

                # rewrite last modified date of corresponding file in objects/files
                exported_filepath = os.path.join(out_folder, dfxml_filename)
                if os.path.isfile(exported_filepath) or os.path.isdir(exported_filepath):
                    os.utime(
                        exported_filepath, (dfxml_filedate, dfxml_filedate)
                    )
        except ValueError:
            print(f"Could not rewrite modified dates for disk {self.image_path} due to Objects.py ValueError")

        self.record_premis(
            timestamp,
            'metadata modification',
            0,
            "DFXML and Python",
            "Corrected file timestamps to match information extracted from disk image",
            "Adapted from Disk Image Processor Version: 1.0.0 (Tessa Walsh)"
            )

    def carve_files_unhfs(self, out_folder, partition):
        self.generate_dfxml_fiwalk()

        print("Carving files using unhfs")
        if sys.platform.startswith("linux"):
            unhfs_path = "/usr/share/hfsexplorer/bin/unhfs"
        elif sys.platform.startswith("darwin"):
            unhfs_path = "/usr/local/share/hfsexplorer/bin/unhfs"

        unhfs_ver_cmd = [unhfs_path]
        unhfs_ver_result = subprocess.run(unhfs_ver_cmd, capture_output=True)
        unhfs_ver = unhfs_ver_result.stderr.decode("utf-8").splitlines()[0]

        if partition:
            unhfs_cmd = [unhfs_path, "-partition", partition["slot"], "-resforks", "APPLEDOUBLE", "-o", out_folder, self.image_path]
        else:
            unhfs_cmd = [unhfs_path, "-resforks", "APPLEDOUBLE", "-o", out_folder, self.image_path]

        timestamp = str(datetime.datetime.now())
        unhfs_result = subprocess.run(unhfs_cmd)
        self.record_premis(
            timestamp,
            'replication',
            unhfs_result.returncode,
            subprocess.list2cmd(unhfs_result.args),
            "Created a bit-wise identical copy of disk image",
            unhfs_ver
        )

    def mount_and_copy_files(self, out_folder):
        print("Mounting image and copying files")
        if self.check_files(out_folder):
            print(f"Files already exist in {out_folder}")
            sys.exit()
        else:
            shutil.rmtree(out_folder)

        mount_location = "/mnt/diskid/"
        mount_cmd = ["sudo", "mount", "-o", "loop", self.image_path, mount_location]
        self.generate_dfxml_walk()

        subprocess.run(mount_cmd)
        timestamp = str(datetime.datetime.now())
        shutil.copytree("/mnt/diskid", out_folder, symlinks=False, ignore=None)
        self.record_premis(
            timestamp,
            "replication",
            0,
            "shutil.copytree",
            "Created a bit-wise identical copy of contents on disk image",
            f"Python {platform.python_version()} shutil"
        )

        unmount_cmd = ["sudo", "umount", mount_location]
        subprocess.run(unmount_cmd)

    def generate_dfxml_fiwalk(self):
        print("Generating DFXML using fiwalk")
        if not os.path.exists(self.dfxml_file):
            timestamp = str(datetime.datetime.now())
            fiwalk_ver_cmd = ["fiwalk", "-V"]
            fiwalk_ver = subprocess.run(fiwalk_ver_cmd, capture_output=True).stdout.decode("utf-8").splitlines()[0]
            fiwalk_cmd = ["fiwalk", "-X", self.dfxml_file, self.image_path]
            fiwalk_result = subprocess.run(fiwalk_cmd)
            self.record_premis(
                timestamp,
                'message digest calculation',
                fiwalk_result.returncode,
                subprocess.list2cmdline(fiwalk_result.args),
                "Extracted information about the structure and characteristics of content on disk image",
                fiwalk_ver
            )

    def generate_dfxml_walk(self):
        print("Generating DFXL using walk_to_dfxml.py")
        this_dir = os.path.dirname(os.path.abspath(__file__))
        walk_to_dfxml_path = os.path.join(this_dir, "walk_to_dfxml.py")
        if not os.path.exists(self.dfxml_file):
            timestamp = str(datetime.datetime.now())
            walk_to_dfxml_cmd = ["python", walk_to_dfxml_path]
            with open(self.dfxml_file, "w") as f:
                walk_to_dfxml_result = subprocess.run(walk_to_dfxml_cmd, cwd="/mnt/diskid/", stdout=f)
            self.record_premis(
                timestamp,
                'message digest calculation',
                walk_to_dfxml_result.returncode,
                subprocess.list2cmdline(walk_to_dfxml_result.args),
                "Extracted information about the structure and characteristics of content on file system",
                "walk_to_dfxml.py"
            )

    def check_files(self, files_dir):
        if not os.path.exists(files_dir):
            return False

        for root, _, filenames in os.walk(files_dir):
            for filename in filenames:
                if os.path.isfile(os.path.join(root, filename)):
                    return True

        return False

    def run_brunnhilde(self):
        print("Running brunnhilde")
        brunnhilde_ver_cmd = ["brunnhilde.py", "-V"]
        brunnhilde_ver = subprocess.run(brunnhilde_ver_cmd, capture_output=True).stdout.decode("utf-8").strip()
        brunnhilde_cmd = ["brunnhilde.py", "-zbn", self.objects_dir, self.brunnhilde_dir]
        timestamp = str(datetime.datetime.now())
        brunnhilde_result = subprocess.run(brunnhilde_cmd)
        self.record_premis(
            timestamp,
            "metadata extraction",
            brunnhilde_result.returncode,
            subprocess.list2cmdline(brunnhilde_result.args),
            "Determined file formats and scanned for potentially sensitive information",
            brunnhilde_ver
        )

    def bag_item(self):
        print("Bagging item")
        bagit_cmd = ["bagit.py", "--md5", self.image_dir]
        subprocess.run(bagit_cmd)


def time_to_int(str_time):
    """ Convert datetime to unix integer value """
    dt = time.mktime(
        datetime.datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%S").timetuple()
    )
    return dt


def list_images(diskimages_dir):
    diskimages_dir_files = os.listdir(diskimages_dir)
    return [filename for filename in diskimages_dir_files if filename.lower().endswith(".iso")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Source directory containing a diskimages directory with one or more disk images")

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source)
    diskimages_dir = os.path.join(source_dir, "diskimages")

    logs_dir = os.path.join(source_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    source_images = list_images(diskimages_dir)
    skipped = []
    for source_image in source_images:
        image_path = os.path.join(diskimages_dir, source_image)
        disk_image_processor = DiskImageProcessor(source_dir, source_image, image_path)
        print(f"Processing {image_path}")
        status, message = disk_image_processor.process_disk()
        if status == "skipped":
            skipped.append(f"{image_path} - {message}")

    if skipped:
        with open(os.path.join(logs_dir, "skipped.txt"), "w") as f:
            f.write("\n".join(skipped))


if __name__ == "__main__":
    main()
