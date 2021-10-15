# Reuther Born-Digital Utilities

This repository contains several Python scripts used in the transfer of born-digital materials at the Walter P. Reuther Library. These utilities are primarily used to assist in the transfer of materials using the Reuther's digital curation workstation.

## Requirements
*Note*: These utilities and their dependencies have been developed and tested on MacOS and Linux operating systems. Some of the dependencies used by the utilities are either unavailable on Windows or would require additional configuration to work within the context of these utilities.

- Python 3: Required to run all utilities
- [brunnhilde](https://github.com/tw4l/brunnhilde) (and related dependencies): Used to generate file format and Bulk Extractor reports
- [bagit](https://github.com/LibraryOfCongress/bagit-python): Used to package transfers

## Installation

- Clone this repository
- `cd reuther_born_digital_utils`
- `git submodule update --init --recursive`
- `pip install -r requirements.txt`

## Usage
The Reuther Born-Digital Utilities are primarily used via the `reuther_bd_accessioner.py` script, which serves as a command line interface to the various transfer methods and types.

`reuther_bd_accessioner.py SOURCE [source_type] [transfer_type]`

Where `SOURCE` is a directory containing one or more transfers, `[source_type]` is one of `--batch [-b]`, `--item [-i]`, or `--nimbie [-n]`, and `[transfer_type]` is one of either `--disk_images [-d]` or `--file_transfer [-f]`

## Tools
The Reuther Born-Digital Utilities make use of various reporting tools to identify file formats, scan for PII, generate technical and preservation metadata for born-digital content, and repackage transfers into Bagit bags. These tools and their purposes include:

- [Brunnhilde](https://github.com/tw4l/brunnhilde), which generates file format reports using Siegfried, scans for PII using bulk extractor, and aggregates the outputs of those tools into an easy to use HTML report
- [disktype](https://linux.die.net/man/1/disktype), which is used to identify the file systems present on a disk image
- [Sleuthkit](https://www.sleuthkit.org/), in particular the utilities `tsk_recover` (to extract contents from disk images), `mmls` to identify partitions on a disk image, and `fiwalk` to generate DFXML (digital forensics XML)
- [hfsexplorer](http://www.catacombae.org/hfsexplorer/), in particular the utility `unhfs` (to extact contents from HFS disk images)
- [DFXML Python scripts](https://github.com/simsong/dfxml) to generate DFXML for a directory (using `walk_to_dfxml.py` and to parse DFXML output (using `Objects.py` and `dfxml.py`)

### Source Types

#### Item
An item source type is used to indicate that the source directory is an individual item or transfer. The accessioning scripts will repackage the contents of the individual item directory into an `objects` subdirectory, and will generate various reports which will be stored in a `metadata` subdirectory. The item will then be bagged.

For example, given the following item directory:

    path/to/transfers/
        LR001542-20181126/
            [transfer contents]

And the following command: `python reuther_bd_accessioner.py path/to/transfers/LR001542-20181126 --item --file_transfer`

Will result in the following package:

    path/to/transfers/
        LR001542-20181126/
            bag-info.txt
            bagit.txt
            manifest-md5.txt
            tagmanifest-md5.txt
            data/
                metadata/
                    submissionDocumentation/
                        dfxml.xml
                        premis.csv
                        brunnhilde/
                            [brunnhilde output]
                objects/
                    [transfer contents]

#### Batch
A batch source type is used to indicate that the source directory contains or more subdirectories, each corresponding to an individual item or transfer. The accessioning script with iterate through each item directory within the batch directory and process each item individually. The batch processor will also create a few high level logs about the status (flagged, skipped, or success) for each item.

For example, given the following batch directory:

    path/to/transfers/
        UR000244/
            UR000244_CD01/
                [item contents]
            UR000244_CD02/
                [item contents]

And the following command: `python reuther_bd_accessioner.py /path/to/transfers/UR000244 --batch --file_transfer`

Will result in the following packages:

    path/to/transfers/
        UR000244/
            batch_transfer_logs/
                flagged.txt
                skipped.txt
                success.txt
            UR000244_CD01/
                [bagit files]
                    data/
                    metadata/
                        submissionDocumentation/
                            dfxml.xml
                            premis.csv
                            brunnhilde/
                                [brunnhilde output]
                    objects/
                        [item contents]
            UR000244_CD02/
                [packaged item similar to CD01]

#### Nimbie
The Nimbie source type is used to indicate that the source directory contains one or more Nimbie batch directories. The accessioning scripts will iterate through each batch directory and through each item directory within each batch directory. The scripts will repackage the batch-level logs and metadata into a `batch_transfer_logs` directory.

For example, given the following Nimbie transfer directory:

    path/to/transfers/
        UR000244/
            UR000244-6a32506e
                batch.log
                manifest.csv
                version.txt
                UR000244_CD01/
                    [contents]
                UR000244_CD02/
                    [contents]
                UR000244_CD03/
                    [contents]
                ...
                UR000244_CD10/
                    [contents]

And the following command: `python reuther_bd_accessioner.py path/to/transfers/UR000244 --nimbie`

Will result in the following:

    path/to/transfers/
        UR000244/
            batch_processor_logs/
                flagged.txt
                skipper.txt
                success.txt
            nimbie_transfer_logs/
                UR000244-6a32506e/
                    batch.log
                    manifest.csv
                    version.txt
            UR000244_CD01/
                [packaged item]
            UR000244_CD02/
                [packaged item]
            UR000244_CD03/
                [packaged item]
            ...
            UR000244_CD10/
                [packaged item]
            

### Transfer Types

#### File Transfer
A transfer type of `--file_transfer [-f]` is used to indicate that the transfer contains one or more items, each consisting of logically copied files. The accessioning scripts will repackage the files into an `objects` directory and run Brunnhilde and various other reporting tools on the repackaged files. All of the above examples in Source Types are file transfers.

#### Disk Images
*Note*: The disk images transfer type is typically only used with legacy disk images in order to extract and identify their contents similar to how we would process those same transfers now. Most transfers going forward will be file transfers, and any disk images that are created will be with the intent that they be preserved as disk images (e.g., video DVDs) and as such should not necessarily be repackaged using these utilities.

A transfer type of `--disk_images [-d]` is used to indicate that the transfer contains one or more items, each consisting of a single .iso disk image. The accessioning scripts will characterize the disk image to determine its file system, extract the contents of the disk image using either tsk_recover, hfsexplorer, or by mounting the disk image and copying the files, and will then run Brunnhilde and various other file format identification and reporting tools on the extracted files similar to the process for file transfers. The accessioning scripts will delete the disk image at the end of processing; this can be overriden with the `--keep_images` flag.

For example, given the following transfer directory:

    path/to/transfers/
        UR000244/
            UR000244_DVD02/
                UR000244_DVD02.iso

And the following command: `python reuther_bd_accessioner.py path/to/transfers/UR000244/UR000244_DVD02 --item --disk_images`

Will result in the following:

    path/to/transfers/
        UR000244/
            UR000244_DVD02/
                [bagit files]
                data/
                    metadata/
                        submissionDocumentation/
                            dfxml.xml
                            disktype.txt
                            premis.csv
                            brunnhilde/
                                [brunnhilde reports]
                    objects/
                        [extracted contents]

  
## Acknowledgments

These scripts were heavily inspired by tools created by Tessa Walsh for the Canadian Centre for Architecture, in particular [diskimageprocessor](https://github.com/CCA-Public/diskimageprocessor) and [folderprocessor](https://github.com/CCA-Public/folderprocessor). Additional inspiration was taken from the Indiana University [Born Digital Preservation Lab ingest tool](https://github.com/IUBLibTech/bdpl_ingest) developed by Mike Shallcross.