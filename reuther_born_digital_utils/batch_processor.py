import os

from reuther_born_digital_utils.item_processor import ItemProcessor


class BatchProcessor:
    def __init__(self, source_dir, transfer_type, keep_image=False):
        self.source_dir = source_dir
        self.transfer_type = transfer_type
        self.keep_image = keep_image
        self.logs_dir = os.path.join(source_dir, "batch_processor_logs")
        self.statuses = {
            "skipped": [],
            "success": [],
            "flagged": []
        }

    def process_batch(self):
        items = [item for item in os.listdir(self.source_dir) if os.path.isdir(os.path.join(self.source_dir, item))]
        for item in items:
            item_dir = os.path.join(self.source_dir, item)
            self.process_item(item_dir)
        self.write_logs()

    def process_item(self, item_dir):
        item_processor = ItemProcessor.processor_for(self.transfer_type)
        processor = item_processor(item_dir, keep_image=self.keep_image)
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
