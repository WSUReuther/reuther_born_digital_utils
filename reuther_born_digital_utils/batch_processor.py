import os
import shutil
import sys

from reuther_born_digital_utils.item_processor import ItemProcessor


class BatchProcessor:
    def __init__(self, source_dir, transfer_type, keep_image=False, nimbie_transfer=False):
        self.source_dir = source_dir
        self.transfer_type = transfer_type
        self.keep_image = keep_image
        self.nimbie_transfer = nimbie_transfer
        self.logs_dir = os.path.join(source_dir, "batch_processor_logs")
        self.statuses = {
            "skipped": [],
            "success": [],
            "flagged": []
        }

    def process_batch(self):
        items = [item for item in os.listdir(self.source_dir) if os.path.isdir(os.path.join(self.source_dir, item)) and item != "nimbie_transfer_logs"]
        for item in items:
            item_dir = os.path.join(self.source_dir, item)
            self.process_item(item_dir)
        self.write_logs()

    def process_item(self, item_dir):
        item_processor = ItemProcessor.processor_for(self.transfer_type)
        processor = item_processor(item_dir, keep_image=self.keep_image, nimbie_transfer=self.nimbie_transfer)
        processor.process()
        item_status = processor.status
        self.statuses[item_status].append(item_dir)

    def write_logs(self):
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)

        for status, items in self.statuses.items():
            status_file = os.path.join(self.logs_dir, f"{status}.txt")
            with open(status_file, "w") as f:
                f.write("\n".join(items))


def process_batch(source_dir, transfer_type, keep_image=False):
    batch_processor = BatchProcessor(source_dir, transfer_type, keep_image=keep_image)
    batch_processor.process_batch()


def process_nimbie_batch(source_dir, transfer_type, keep_image=False):
    batch_dirs = [item for item in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, item))]
    for batch_dir in batch_dirs:
        batch_dirpath = os.path.join(source_dir, batch_dir)
        if not os.path.exists(os.path.join(batch_dirpath, "batch.log")):
            sys.exit(f"This does not look like a Nimbie transfer: batch.log not found at {batch_dirpath}")
        transfer_files = [item for item in os.listdir(batch_dirpath) if os.path.isfile(os.path.join(batch_dirpath, item))]
        transfer_logs_dir = os.path.join(source_dir, "nimbie_transfer_logs", batch_dir)
        os.makedirs(transfer_logs_dir)
        for transfer_file in transfer_files:
            shutil.move(os.path.join(batch_dirpath, transfer_file), transfer_logs_dir)
        transfer_items = [item for item in os.listdir(batch_dirpath) if os.path.isdir(os.path.join(batch_dirpath, item))]
        for transfer_item in transfer_items:
            item_path = os.path.join(batch_dirpath, transfer_item)
            shutil.move(item_path, source_dir)
        os.rmdir(batch_dirpath)
    batch_processor = BatchProcessor(source_dir, transfer_type, keep_image=keep_image, nimbie_transfer=True)
    batch_processor.process_batch()
