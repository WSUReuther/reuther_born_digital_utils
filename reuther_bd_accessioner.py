import argparse
import sys

from reuther_born_digital_utils.batch_processor import process_batch
from reuther_born_digital_utils.item_processor import process_item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Source directory containing transfer materials")
    parser.add_argument(
                        "-d", "--disk_images",
                        help="Process disk images in source directory",
                        action="store_true"
                        )
    parser.add_argument(
                        "-k", "--keep_image",
                        help="Kee disk image after extracting files",
                        action="store_true"
                        )
    parser.add_argument(
                        "-f", "--file_transfer",
                        help="Process file transfers in source directory",
                        action="store_true"
                        )
    parser.add_argument(
                        "-b", "--batch",
                        help="Source directory is a batch containing one or more item subdirectories",
                        action="store_true"
                        )
    parser.add_argument(
                        "-i", "--item",
                        help="Source directory is an individual item",
                        action="store_true"
                        )
    args = parser.parse_args()

    source_dir = args.source
    if args.disk_images and not args.file_transfer:
        transfer_type = "disk_images"
    elif args.file_transfer and not args.disk_images:
        transfer_type = "folders"
    else:
        sys.exit("Please specify either a disk image transfer [-d] or a file transfer transfer [-f]")

    if args.batch and not args.item:
        source_type = "batch"
    elif args.item and not args.batch:
        source_type = "item"
    else:
        sys.exit("Please specify either a batch transfer [-b] or an individual item transfer [-i]")

    if source_type == "batch":
        process_batch(source_dir, transfer_type, args.keep_image)
    else:
        process_item(source_dir, transfer_type, args.keep_image)


if __name__ == "__main__":
    main()
