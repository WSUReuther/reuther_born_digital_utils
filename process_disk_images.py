# Process legacy disk images (extract contents and run various reports on images and files)
# Heavily inspired by/adopted from Tessa Walsh's diskimageprocessor (https://github.com/CCA-Public/diskimageprocessor)

import argparse
import datetime
import os
import subprocess
import time

import Objects


def time_to_int(str_time):
    """ Convert datetime to unix integer value """
    dt = time.mktime(
        datetime.datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%S").timetuple()
    )
    return dt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Source directory containing a diskimages directory with one or more disk images")

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source)
    diskimages_dir = os.path.join(source_dir, "diskimages")

    logs_dir = os.path.join(source_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    source_images = os.listdir(diskimages_dir)
    skipped = []
    for source_image in source_images:
        if source_image.lower().endswith((".e01", ".000", ".001", ".raw", ".img", ".dd", ".iso")):
            image_path = os.path.join(diskimages_dir, source_image)
            print(f"Processing {image_path}")
            image_filename, image_ext = os.path.splitext(source_image)

            # create new folders
            sip_dir = os.path.join(source_dir, image_filename)
            objects_dir = os.path.join(sip_dir, "objects")
            metadata_dir = os.path.join(sip_dir, "metadata")
            subdoc_dir = os.path.join(metadata_dir, "submissionDocumentation")
            brunnhilde_dir = os.path.join(subdoc_dir, "brunnhilde")
            for folder in [sip_dir, objects_dir, metadata_dir, subdoc_dir]:
                os.makedirs(folder)

            isoinfo_txt = os.path.join(subdoc_dir, "isoinfo_list.txt")
            subprocess.call("isoinfo -f -i '%s' > '%s'" % (image_path, isoinfo_txt), shell=True)

            potential_video = False
            for line in open(isoinfo_txt, "r"):
                if line.strip() in ["/AUDIO_TS", "/VIDEO_TS"]:
                    potential_video = True

            if potential_video:
                print(f"Skipping {image_path}: potential video")
                skipped.append(image_path)
                continue

            disktype_txt = os.path.join(subdoc_dir, "disktype.txt")
            subprocess.call("disktype '%s' > '%s'" % (image_path, disktype_txt), shell=True)

            disk_fs = ""
            try:
                for line in open(disktype_txt, "r"):
                    if "file system" in line:
                        disk_fs = line.strip()
            except:
                for line in open(disktype_txt, "rb"):
                    if "file system" in line.decode("utf-8", "ignore"):
                        disk_fs = line.decode("utf-8", "ignore").strip()

            if any(
                x in disk_fs.lower()
                for x in (
                    "ntfs",
                    "fat",
                    "ext",
                    "iso9660",
                    "hfs+",
                    "ufs",
                    "raw",
                    "swap",
                    "yaffs2",
                )
            ):
                fiwalk_file = os.path.join(subdoc_dir, "dfxml.xml")

                print("Generating DFXML")
                subprocess.check_output(["fiwalk", "-X", fiwalk_file, image_path])

                print("Running tsk_recover")
                subprocess.check_output(["tsk_recover", "-a", image_path, objects_dir])

                print("Updating modified times from DFXML")
                try:
                    for (event, obj) in Objects.iterparse(fiwalk_file):
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
                        exported_filepath = os.path.join(objects_dir, dfxml_filename)
                        if os.path.isfile(exported_filepath) or os.path.isdir(exported_filepath):
                            os.utime(
                                exported_filepath, (dfxml_filedate, dfxml_filedate)
                            )
                except ValueError:
                    print(f"Could not rewrite modified dates for disk {image_path} due to Objects.py ValueError")

                print("Running Brunnhilde")
                subprocess.call(
                    "brunnhilde.py -zb '%s' '%s'" % (objects_dir, brunnhilde_dir),
                    shell=True
                )
                print("Bagging image")
                subprocess.call("bagit.py --md5 '%s'" % (sip_dir), shell=True)

    if skipped:
        with open(os.path.join(logs_dir, "skipped.txt"), "w") as f:
            f.write("\n".join(skipped))


if __name__ == "__main__":
    main()
