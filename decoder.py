'''
    2017
    Margarida Reis & Hugo Silva
    Técnico Lisboa
    IT - Instituto de Telecomunicações

    Made in Portugal

    Acknowledgments: This work was partially supported by the IT – Instituto de Telecomunicações
    under the grant UID/EEA/50008/2013 "SmartHeart" (https://www.it.pt/Projects/Index/4465).
'''

from __future__ import division
import argparse
import sys
import os
import stat
import json
from datetime import datetime
import timeit
import struct
import numpy as np
import math
import itertools
import seaborn as sns
import matplotlib.pyplot as plt
from collections import OrderedDict

np.set_printoptions(suppress=True, linewidth=80)
sns.set(context='paper', style='ticks', font_scale=1.2)
plt.rcParams['agg.path.chunksize'] = 20000

no_files = 0
file_no = 0
output_log = None


def to_json_2(o, level=0):
    indent = 2
    space = u' '
    newline = u'\n'
    ret = u''
    if isinstance(o, dict):
        ret += u"{" + newline
        comma = u""
        for k,v in o.items():
            ret += comma
            comma = u",\n"
            ret += space * indent * (level+1)
            ret += u'"' + unicode(k) + u'":' + space
            ret += to_json_2(v, level + 1)

        ret += newline + space * indent * level + u"}"
    elif isinstance(o, basestring):
        ret += u'"' + o + u'"'
    elif isinstance(o, list):
        ret += u"[" + u",".join([to_json_2(e, level+1) for e in o]) + u"]"
    elif isinstance(o, bool):
        ret += u"true" if o else u"false"
    elif isinstance(o, int):
        ret += unicode(o)
    elif isinstance(o, float):
        ret += u'%.7g' % o
    elif isinstance(o, np.ndarray) and np.issubdtype(o.dtype, np.integer):
        ret += u"[" + u','.join(imap(unicode, o.flatten().tolist())) + u"]"
    elif isinstance(o, np.ndarray) and np.issubdtype(o.dtype, np.inexact):
        ret += u"[" + u','.join(imap(lambda x: u'%.7g' % x, o.flatten().tolist())) + u"]"
    elif o is None:
        ret += u'null'
    else:
        raise TypeError(u"Unknown type '%s' for json serialization" % unicode(type(o)))
    return ret


def to_json_3(o, level=0):
    indent = 2
    space = ' '
    newline = '\n'
    ret = ''
    if isinstance(o, dict):
        ret += "{" + newline
        comma = ""
        for k,v in o.items():
            ret += comma
            comma = ",\n"
            ret += space * indent * (level+1)
            ret += '"' + str(k) + '":' + space
            ret += to_json_3(v, level + 1)

        ret += newline + space * indent * level + "}"
    elif isinstance(o, str):
        ret += '"' + o + '"'
    elif isinstance(o, list):
        ret += "[" + ",".join([to_json_3(e, level+1) for e in o]) + "]"
    elif isinstance(o, bool):
        ret += "true" if o else "false"
    elif isinstance(o, int):
        ret += str(o)
    elif isinstance(o, float):
        ret += '%.7g' % o
    elif isinstance(o, np.ndarray) and np.issubdtype(o.dtype, np.integer):
        ret += "[" + ','.join(map(str, o.flatten().tolist())) + "]"
    elif isinstance(o, np.ndarray) and np.issubdtype(o.dtype, np.inexact):
        ret += "[" + ','.join(map(lambda x: '%.7g' % x, o.flatten().tolist())) + "]"
    elif o is None:
        ret += 'null'
    else:
        raise TypeError("Unknown type '%s' for json serialization" % str(type(o)))
    return ret


def chunk_string(string, length):
    return (string[0+i:length+i] for i in range(0, len(string), length))


def conversion_progress(percentage):
    print(percentage, '%')


def encode_opensignals_header(decoded):
    # this methods creates an OpenSignals-compatible dump file from the OpenLog one by encoding the header
    sampling_rate = decoded['settings']['sampling rate']

    json_channels = decoded['settings']['channels']
    no_channels = len(json_channels)
    channels = []
    for i in range(0, no_channels):
        channels.append('A' + str(json_channels[i]))

    if no_channels == 6:
        adc_resolution = [10, 10, 10, 10, 6, 6]
    elif no_channels == 5:
        adc_resolution = [10, 10, 10, 10, 6]
    else:
        adc_resolution = [10] * no_channels

    mode = 0
    json_mode = decoded['settings']['mode']
    if json_mode == 'simulated':
        mode = 1

    aux_json_settings = OrderedDict()
    aux_json_settings['sensor'] = ['RAW'] * no_channels
    aux_json_settings['device name'] = 'xx:xx:xx:xx:xx:xx'
    aux_json_settings['column'] = ['nSeq', 'I1', 'I2', 'O1', 'O2'] + channels
    aux_json_settings['sync interval'] = 2
    aux_json_settings['time'] = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    aux_json_settings['comments'] = ''
    aux_json_settings['device connection'] = 'OpenLog'
    aux_json_settings['channels'] = json_channels
    aux_json_settings['date'] = datetime.now().strftime('%Y-%m-%d')
    aux_json_settings['mode'] = mode
    aux_json_settings['digital IO'] = [0, 0, 1, 1]
    aux_json_settings['firmware version'] = 52
    aux_json_settings['device'] = 'bitalino_rev'
    aux_json_settings['position'] = 0
    aux_json_settings['sampling rate'] = sampling_rate
    aux_json_settings['label'] = channels
    aux_json_settings['resolution'] = [4, 1, 1, 1, 1] + adc_resolution
    aux_json_settings['special'] = ''
    json_settings = OrderedDict()
    json_settings['xx:xx:xx:xx:xx:xx'] = aux_json_settings

    header = 'OpenSignals Text File Format' + '\n' + \
             json.dumps(json_settings) + '\n' + \
             'EndOfHeader'

    return header


def decode_bin_to_ascii(openlog_filename, opensignals_filename, callback, no_bytes_to_read=0, from_what=0):
    if no_bytes_to_read == 0 and from_what == 0:
        print("READING all bytes from the file")
    else:
        print("READING", no_bytes_to_read, "bytes from the file")
        print("STARTING at byte #", from_what)
        read_no_bytes = 0

    packet_no = 0
    decoded_packets = 0
    percentage = 0
    crc_fails = 0
    total_failed_pckts = 0
    last_seq_no = 0
    failed_nSeq = []
    failed_indices = []
    with open(opensignals_filename, 'wb') as opensignals_file, open(openlog_filename, 'rb') as openlog_file:
        header = openlog_file.readline()
        header_tell = openlog_file.tell()
        if openlog_file.readline() == b'\r\n':  # filter out any extra lines
            openlog_file.seek(openlog_file.tell())
        else:
            openlog_file.seek(header_tell)
        header = header.rstrip()
        csv_line = header[2:].decode('utf-8')
        csv_settings = csv_line.split(',')
        channels = ''.join(n for n in csv_settings[2] if n.isdigit())
        no_channels = len(channels)
        sampling_rate = int(csv_settings[0])

        print(csv_settings)

        decoded = {}
        decoded['settings'] = {}
        decoded['settings']['channels'] = channels
        decoded['settings']['sampling rate'] = sampling_rate
        decoded['settings']['mode'] = csv_settings[1]
        header = encode_opensignals_header(decoded)
        np.savetxt(opensignals_file, [], header=header)

        if no_channels <= 4:
            no_bytes = int(math.ceil((12. + 10. * no_channels) / 8.))
        else:
            no_bytes = int(math.ceil((52. + 6. * (no_channels - 4)) / 8.))

        header_size = openlog_file.tell()
        total_size = os.fstat(openlog_file.fileno()).st_size
        no_packets = int((total_size - header_size)/no_bytes)
        percentage_progress = int(round(no_packets/100))
        print("PACKETS:", no_packets)
        sampling_time = no_packets/(60*sampling_rate)
        print("~", sampling_time, "minutes =", no_packets/(3600*sampling_rate), "hours")

        while True:
            if no_bytes_to_read == 0 and from_what == 0:
                openlog_file.seek(openlog_file.tell())
                raw_data = openlog_file.read(no_bytes)
                if not raw_data:
                    break
            else:
                openlog_file.seek(openlog_file.tell()+from_what)
                raw_data = openlog_file.read(no_bytes)
                read_no_bytes += no_bytes
                if read_no_bytes > no_bytes_to_read:
                    break
            # print(''.join('\\x{:02x}'.format(letter) for letter in raw_data))
            if len(raw_data) == no_bytes:
                decoded_data = list(struct.unpack(no_bytes * "B ", raw_data))
                crc = decoded_data[-1] & 0x0F
                decoded_data[-1] = decoded_data[-1] & 0xF0
                # the BITalino method from the APIs for calculating the CRC
                x = 0
                for i in range(no_bytes):
                    for bit in range(7, -1, -1):
                        x = x << 1
                        if x & 0x10:
                            x = x ^ 0x03
                        x = x ^ ((decoded_data[i] >> bit) & 0x01)
                # alternate method for calculating the CRC
                # x0, x1, x2, x3, out, inp = 0, 0, 0, 0, 0, 0
                # for i in range(no_bytes):
                #     for bit in range(7, -1, -1):
                #         inp = (decoded_data[i]) >> bit & 0x01
                #         # if i == (no_bytes - 1) and bit < 4:
                #         #     inp = 0
                #         out = x3
                #         x3 = x2
                #         x2 = x1
                #         x1 = out ^ x0
                #         x0 = inp ^ out
                # x = ((x3 << 3) | (x2 << 2) | (x1 << 1) | x0)
                if crc == x & 0x0F:  # only fill data to the array if it passes CRC verification
                    decoded_packets += 1
                    data_acquired = np.zeros(5 + no_channels)
                    last_seq_no = data_acquired[0] = decoded_data[-1] >> 4  # sequence number
                    data_acquired[1] = decoded_data[-2] >> 7 & 0x01
                    data_acquired[2] = decoded_data[-2] >> 6 & 0x01
                    data_acquired[3] = decoded_data[-2] >> 5 & 0x01
                    data_acquired[4] = decoded_data[-2] >> 4 & 0x01
                    if no_channels > 0:
                        data_acquired[5] = ((decoded_data[-2] & 0x0F) << 6) | (decoded_data[-3] >> 2)
                    if no_channels > 1:
                        data_acquired[6] = ((decoded_data[-3] & 0x03) << 8) | decoded_data[-4]
                    if no_channels > 2:
                        data_acquired[7] = (decoded_data[-5] << 2) | (decoded_data[-6] >> 6)
                    if no_channels > 3:
                        data_acquired[8] = ((decoded_data[-6] & 0x3F) << 4) | (decoded_data[-7] >> 4)
                    if no_channels > 4:
                        data_acquired[9] = ((decoded_data[-7] & 0x0F) << 2) | (decoded_data[-8] >> 6)
                    if no_channels > 5:
                        data_acquired[10] = decoded_data[-8] & 0x3F
                    np.savetxt(opensignals_file, [data_acquired], delimiter='\t', fmt='%i')
                else:  # CRC fail
                    crc_fails += 1
                    failed_indices.append(packet_no)
                    fail_time = packet_no/sampling_rate/60
                    print("CRC FAIL @", fail_time, "minutes =", fail_time/60, "hours")
                    realigned = False
                    first_shift = True
                    while realigned is False:
                        # shift byte-by-byte
                        if first_shift is True:
                            openlog_file.seek(openlog_file.tell())
                            first_shift = False
                        else:
                            openlog_file.seek(openlog_file.tell()-no_bytes+1)
                        raw_data = openlog_file.read(no_bytes)
                        # print(''.join('\\x{:02x}'.format(letter) for letter in raw_data))
                        if len(raw_data) == no_bytes:
                            decoded_data = list(struct.unpack(no_bytes * "B ", raw_data))
                            crc = decoded_data[-1] & 0x0F
                            decoded_data[-1] = decoded_data[-1] & 0xF0
                            x = 0
                            for i in range(no_bytes):
                                for bit in range(7, -1, -1):
                                    x = x << 1
                                    if x & 0x10:
                                        x = x ^ 0x03
                                    x = x ^ ((decoded_data[i] >> bit) & 0x01)
                            if crc == x & 0x0F:
                                decoded_packets += 1
                                data_acquired = np.zeros(5 + no_channels)
                                realigned_seq_no = data_acquired[0] = decoded_data[-1] >> 4  # sequence number
                                data_acquired[1] = decoded_data[-2] >> 7 & 0x01
                                data_acquired[2] = decoded_data[-2] >> 6 & 0x01
                                data_acquired[3] = decoded_data[-2] >> 5 & 0x01
                                data_acquired[4] = decoded_data[-2] >> 4 & 0x01
                                if no_channels > 0:
                                    data_acquired[5] = ((decoded_data[-2] & 0x0F) << 6) | (decoded_data[-3] >> 2)
                                if no_channels > 1:
                                    data_acquired[6] = ((decoded_data[-3] & 0x03) << 8) | decoded_data[-4]
                                if no_channels > 2:
                                    data_acquired[7] = (decoded_data[-5] << 2) | (decoded_data[-6] >> 6)
                                if no_channels > 3:
                                    data_acquired[8] = ((decoded_data[-6] & 0x3F) << 4) | (decoded_data[-7] >> 4)
                                if no_channels > 4:
                                    data_acquired[9] = ((decoded_data[-7] & 0x0F) << 2) | (decoded_data[-8] >> 6)
                                if no_channels > 5:
                                    data_acquired[10] = decoded_data[-8] & 0x3F
                                np.savetxt(opensignals_file, [data_acquired], delimiter='\t', fmt='%i')
                                if realigned_seq_no < last_seq_no:
                                    no_failed_pckts = 15 - last_seq_no + realigned_seq_no
                                elif realigned_seq_no == last_seq_no:
                                    no_failed_pckts = 15
                                else:
                                    no_failed_pckts = realigned_seq_no - last_seq_no - 1
                                total_failed_pckts += no_failed_pckts
                                realigned = True
                                failed_nSeq.append((last_seq_no, realigned_seq_no))
                                print("SEQUENCE REALIGNED")
                                print(no_failed_pckts, "PACKET(s) LOST:", last_seq_no, realigned_seq_no, "\n")
                packet_no += 1
                if decoded_packets == percentage_progress:
                    decoded_packets = 0
                    percentage += 1
                    # do not print values such as 101% (may occur dur to rounding the # of packets)
                    if percentage <= 100:
                        callback(percentage)

    failed_nSeq = np.asanyarray(failed_nSeq)

    decoded['sampling time'] = sampling_time
    decoded['lost packets'] = total_failed_pckts
    decoded['failed nSeq'] = failed_nSeq
    decoded['failed indices'] = failed_indices

    print("DONE!")

    return decoded


def plot_decoded(opensignals_filename, decoded_json):
    data = np.loadtxt(opensignals_filename, delimiter='\t')  # read the file

    no_channels = len(decoded_json['settings']['channels'])
    rows = int(2 + math.ceil(no_channels/2))

    fig, ax = plt.subplots(rows, 2)  # rows, columns
    fig.suptitle("TIME DOMAIN: decoded data")

    n = np.shape(data)[0]
    x = np.arange(n) / decoded_json['settings']['sampling rate']

    palette = itertools.cycle(sns.hls_palette(n_colors=no_channels+4, s=0.6, l=0.6))
    io_title = ['I1', 'I2', 'O1', 'O2']

    i = 0
    for row in ax:
        for col in row:
            if i < no_channels:
                title = 'A' + str(decoded_json['settings']['channels'][i])
                y = data[:, 5+i]
            else:
                try:
                    title = io_title[i - no_channels]
                    y = data[:, i - no_channels + 1]
                except IndexError:
                    break
            col.plot(x, y, color=next(palette), linewidth=1.5)
            col.set_title(title)
            i += 1

    for aux in fig.get_axes():
        aux.grid(linestyle='--')

    fig_mng = plt.get_current_fig_manager()
    # fig_mng.resize(*fig_mng.window.maxsize())  # for linux
    fig_mng.window.state('zoomed')  # for windows

    plt.subplots_adjust(left=0.05, bottom=0.05, right=0.95, top=0.93, wspace=0.1, hspace=0.55)
    plt.show()


def decode(openlog_filename, no_bytes_to_read=0, from_what=0):
    local_file = os.path.normpath(openlog_filename)
    (local_dir_name, local_base_filename) = os.path.split(local_file)
    (local_base_filename, local_filename_suffix) = os.path.splitext(local_base_filename)
    if local_filename_suffix == '.BIN':
        global file_no
        file_no += 1
        print("FILE", file_no, "of", no_files)
        print(openlog_filename)
        opensignals_filename = os.path.join(local_dir_name, local_base_filename + '.TXT')
        start = timeit.default_timer()
        decoded = decode_bin_to_ascii(openlog_filename=openlog_filename,
                                      opensignals_filename=opensignals_filename,
                                      callback=conversion_progress,
                                      no_bytes_to_read=no_bytes_to_read,
                                      from_what=from_what)
        end = timeit.default_timer()
        decoding_time = ((end - start) / 60)  # total time in minutes
        # print("TOTAL TIME :", (end - start), "seconds =", decoding_time, " minutes")

        aux_json_decoded = OrderedDict()
        # the previous directory must always be named after the card type!
        aux_json_decoded['card type'] = local_dir_name[local_dir_name.rfind(os.sep)+1:]
        aux_json_decoded['# of channels'] = len(decoded['settings']['channels'])
        aux_json_decoded['sampling rate [Hz]'] = decoded['settings']['sampling rate']
        aux_json_decoded['mode'] = decoded['settings']['mode']
        aux_json_decoded['sampling time [mins]'] = decoded['sampling time']
        aux_json_decoded['decoding time [mins]'] = decoding_time
        aux_json_decoded['# of CRC fails'] = len(decoded['failed nSeq'])
        aux_json_decoded['# of lost packets'] = decoded['lost packets']
        aux_json_decoded['failed nSeq'] = decoded['failed nSeq'].tolist()
        aux_json_decoded['failed indices'] = decoded['failed indices']
        json_decoded = OrderedDict()
        openlog_filename = openlog_filename.replace('\\', '/')
        json_decoded[openlog_filename] = aux_json_decoded

        if python2:
            output_log.write(to_json_2(o=json_decoded))
            output_log.write(u'\n')
        elif python3:
            output_log.write(to_json_3(o=json_decoded))
            output_log.write('\n')

        print(json_decoded)
        print('\n')

        # plot_decoded(opensignals_filename, decoded)
    else:
        print("\nThe filename specified does not correspond to a .BIN file\n")


def walktree(top, calls=1, callback=decode):
    if calls == 1:
        local_st_mode = os.stat(top).st_mode
        global no_files
        if stat.S_ISREG(local_st_mode):  # give the user the option to decode a single file and not an entire directory
            no_files = 1
            callback(openlog_filename=top)  # adjust here the no_bytes and from_what argument if desired
            return
        elif stat.S_ISDIR(local_st_mode):
            for _, _, local_filenames in os.walk(top):
                for local_file in local_filenames:
                    (local_dir_name, local_base_filename) = os.path.split(local_file)
                    (local_base_filename, local_filename_suffix) = os.path.splitext(local_base_filename)
                    if local_filename_suffix == '.BIN':
                        no_files += 1
        else:
            # unknown file type, print a message
            print("WARNING: skipping %s" % top)
    for f in os.listdir(top):
        local_pathname = os.path.join(top, f)
        local_st_mode = os.stat(local_pathname).st_mode
        if stat.S_ISDIR(local_st_mode):
            # it's a directory, recurse into it
            walktree(local_pathname, calls=calls+1, callback=callback)
        elif stat.S_ISREG(local_st_mode):
            # it's a file, call the callback function
            callback(openlog_filename=local_pathname)  # adjust here the no_bytes and from_what argument if desired
        else:
            # unknown file type, print a message
            print("WARNING: skipping %s" % local_pathname)


def main(arguments):
    parser = argparse.ArgumentParser(description='decoder from BIN (OpenLog) to ASCII (OpenSignals)')
    # give the user the option to decode a single file and not an entire directory
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-p', '--pathname', help='the pathname of the folder to decode')
    group.add_argument('-f', '--filename', help='the filename of the single file to decode')
    args = parser.parse_args(arguments)

    ok = False
    if args.pathname:
        pathname = args.pathname
        pathname = pathname.lstrip()
        stat_mode = os.stat(pathname).st_mode
        if stat.S_ISDIR(stat_mode):  # check that it is indeed a folder
            print("\nDECODE directory\n")
            output_log_name = os.path.join(pathname, pathname[pathname.rfind(os.sep) + 1:] + '.LOG')
            ok = True
        else:
            print("\nThe pathname specified does not correspond to an actual folder")
    elif args.filename:
        pathname = args.filename
        pathname = pathname.lstrip()
        stat_mode = os.stat(pathname).st_mode
        if stat.S_ISREG(stat_mode):  # check that it is indeed a file
            print("\nDECODE file\n")
            file = os.path.normpath(pathname)
            (dir_name, base_filename) = os.path.split(file)
            (base_filename, filename_suffix) = os.path.splitext(base_filename)
            output_log_name = os.path.join(dir_name, base_filename + '.LOG')
            ok = True
        else:
            print("\nThe filename specified does not correspond to an actual file")

    if ok is True:
        global output_log
        output_log = open(output_log_name, 'w')
        walktree(pathname)
        output_log.close()
        print("ALL DONE!")


if __name__ == "__main__":
    if sys.version_info[0] == 3:
        python2 = False
        python3 = True
        print("\nPyhton 3")
    elif sys.version_info[0] == 2:
        python2 = True
        python3 = False
        print("\nPython 2")
        from itertools import imap
        from io import open
    main(sys.argv[1:])
    # amp = 1023
    # rises = np.where(np.diff(decoded['data'][:, 5]) == amp)[0]
    # falls = np.where(np.diff(decoded['data'][:, 5]) == -amp)[0]
    #
    # print(len(decoded['data'][:, 5]))
    # print(len(rises), rises)
    # print(len(falls), falls)
