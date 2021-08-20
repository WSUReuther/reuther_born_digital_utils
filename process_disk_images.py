# Process legacy disk images (extract contents and run various reports on images and files)
# Heavily inspired by/adopted from Tessa Walsh's diskimageprocessor (https://github.com/CCA-Public/diskimageprocessor)
# Additional inspiration from Mike Shallcross (https://github.com/IUBLibTech/bdpl_ingest)

import argparse
import datetime
import os
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

        self.setup_dirs()

    def setup_dirs(self):
        image_filename, image_ext = os.path.splitext(self.source_image)
        self.image_dir = os.path.join(self.source_dir, image_filename)
        self.objects_dir = os.path.join(self.image_dir, "objects")
        self.metadata_dir = os.path.join(self.image_dir, "metadata")
        self.subdoc_dir = os.path.join(self.metadata_dir, "submissionDocumentation")
        self.dfxml_file = os.path.join(self.subdoc_dir, "dfxml.xml")
        self.brunnhilde_dir = os.path.join(self.subdoc_dir, "brunnhilde")
        for dirpath in [self.image_dir, self.objects_dir, self.metadata_dir, self.subdoc_dir]:
            os.makedirs(dirpath)

    def process_disk(self):
        status = ""
        self.run_preliminary_tools()
        potential_video = self.check_for_video()
        if potential_video:
            status = "skipped"
            return status
        else:
            self.characterize_and_extract_files()
            self.run_brunnhilde()

    def run_preliminary_tools(self):
        self.isoinfo_txt = os.path.join(self.subdoc_dir, "isoinfo_list.txt")
        isoinfo_cmd = f"isoinfo -f -i '{self.image_path}' > '{self.isoinfo_txt}'"
        subprocess.call(isoinfo_cmd, shell=True)

        self.disktype_txt = os.path.join(self.subdoc_dir, "disktype.txt")
        disktype_cmd = f"disktype '{self.image_path}' > '{self.disktype_txt}'"
        subprocess.call(disktype_cmd, shell=True)

    def check_for_video(self):
        potential_video = False
        for line in open(self.isoinfo_txt, "r"):
            if line.strip() in ["/AUDIO_TS", "/VIDEO_TS"]:
                potential_video = True
        return potential_video

    def characterize_and_extract_files(self):
        self.parse_disk_filesystems()

        if len(self.partition_info_list) <= 1:
            self.handle_file_extraction(self.objects_dir, False)
        else:
            for partition_info in self.partition_info_list:
                out_folder = os.path.join(self.objects_dir, f"partition_{partition_info['slot']}")
                self.handle_file_extraction(out_folder, partition_info)

    def parse_disk_filesystems(self):
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
            mmls_output = os.path.join(self.subdoc_dir, "mmls_output.txt")
            mmls_command = f"mmls {self.image_path} > {mmls_output}"
            subprocess.call(mmls_command, shell=True, text=True)
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
            # hybrid disk
            filesystem = "iso9660"
        else:
            # skip
            pass

        if filesystem in self.tsk_list:
            self.carve_files_tsk(out_folder, partition)
        elif filesystem in self.unhfs_list:
            self.carve_files_unhfs(out_folder, partition)
        elif filesystem in self.mount_and_copy_list:
            self.mount_and_copy_files(out_folder)
        else:
            # do something here to log that the filesystem is unsupported
            pass

    def carve_files_tsk(self, out_folder, partition):
        self.generate_dfxml_fiwalk()
        if partition:
            tsk_cmd = f"tsk_recover -a -o {partition['start']} {self.image_path} {out_folder}"
        else:
            tsk_cmd = f"tsk_recover -a {self.image_path} {out_folder}"
        subprocess.call(tsk_cmd, shell=True)
        self.fix_dates(out_folder)

    def fix_dates(self, out_folder):
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
            print(f"Could not rewrite modified dates for disk {image_path} due to Objects.py ValueError")

    def carve_files_unhfs(self, out_folder, partition):
        self.generate_dfxml_fiwalk()
        if sys.platform.startswith("linux"):
            unhfs_path = "/usr/share/hfsexplorer/bin/unhfs"
        elif sys.platform.startswith("darwin"):
            unhfs_path = "/usr/local/share/hfsexplorer/bin/unhfs"

        if partition:
            unhfs_cmd = f'{unhfs_path} -partition {partition["slot"]} -resforks APPLEDOUBLE -o "{out_folder}" "{self.image_path}"'
        else:
            unhfs_cmd = f'{unhfs_path} -resforks APPLEDOUBLE -o "{out_folder}" "{self.image_path}"'

        subprocess.call(unhfs_cmd, shell=True)

    def mount_and_copy_files(self, out_folder):
        if self.check_files(out_folder):
            print(f"Files already exist in {out_folder}")
            sys.exit()
        else:
            shutil.rmtree(out_folder)

        mount_cmd = f"sudo mount -o loop '{self.image_path}' /mnt/diskid/"
        self.generate_dfxml_walk()

        subprocess.call(mount_cmd, shell=True)
        shutil.copytree("/mnt/diskid", out_folder, symlinks=False, ignore=None)
        subprocess.call("sudo umount /mnt/diskid", shell=True)

    def generate_dfxml_fiwalk(self):
        if not os.path.exists(self.dfxml_file):
            fiwalk_cmd = ["fiwalk", "-X", self.dfxml_file, self.image_path]
            subprocess.check_output(fiwalk_cmd)

    def generate_dfxml_walk(self):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        walk_to_dfxml_path = os.path.join(this_dir, "walk_to_dfxml.py")
        if not os.path.exists(self.dfxml_file):
            walk_to_dfxml_cmd = f"cd /mnt/diskid/ && python {walk_to_dfxml_path} > '{self.dfxml_file}'"
            subprocess.call(walk_to_dfxml_cmd, shell=True)

    def check_files(self, files_dir):
        if not os.path.exists(files_dir):
            return False

        for root, _, filenames in os.walk(files_dir):
            for filename in filenames:
                if os.path.isfile(os.path.join(root, filename)):
                    return True

        return False

    def run_brunnhilde(self):
        brunnhilde_cmd = f"brunnhilde.py -zb '{self.objects_dir}' '{self.brunnhilde_dir}'"
        subprocess.call(brunnhilde_cmd, shell=True)

    def bag_item(self):
        bagit_cmd = f"bagit.py --md5 '{self.image_dir}'"
        subprocess.call(bagit_cmd, shell=True)


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
        status = disk_image_processor.process_disk()
        if status == "skipped":
            skipped.append(image_path)

    if skipped:
        with open(os.path.join(logs_dir, "skipped.txt"), "w") as f:
            f.write("\n".join(skipped))


if __name__ == "__main__":
    main()
