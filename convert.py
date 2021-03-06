#!/usr/bin/env python
from bitstring import BitStream, BitArray, Bits
from bitarray import bitarray
import sys, argparse, binascii, math, time
import multiprocessing as mp
import random

#define the length in bits of a character
char_length = 8
parity_positions = []
total_chars = mp.Value('i', 0)

'''
INPUT:
	char_hammingArray: bitarry to store the hamming code of a character
	bit: the 0 indexed position within char_hammingArray of the parity bit of interest
OUTPUT: the checksum for the provided bit
'''
def calc_checksum(char_hammingArray, bit):
	pos = bit
	#increment bit by 1 so it's 1 indexed instead of 0 indexed
	bit+=1
	check_sum = 0
	#indicate if skipping or checking while iterating down char_hammingArray
	flip_ind = 0
	#pos starts at the parity bit position each iteration and is incremented by 1 until it exceeds the length of the char_hammingArray
	while (pos < len(char_hammingArray)-1):
		check_sum += char_hammingArray[pos]
		flip_ind += 1
		if(flip_ind == bit):
			pos += bit
			flip_ind = 0
		pos+=1
	return check_sum

'''
INPUT:
	character: character as a string
	parity_positions: array of integers representing 0 indexed positions of parity bits for a character
OUTPUT:
	char_hammingArray: bitarray of length char_length plus number of parity bits encoded with (8,12) Hamming Code
'''
def set_hammingArray(character):
	#make a bitarray for the input character
	char_bitarray = BitArray('int:8='+str(ord(character)))
	#make a bit array to hold the channel coded version of the character.
	char_hammingArray = BitArray('0b0000000000000')
	#transfer all bits from the char_bitarray to the char_hammingArray skipping the parity bit positions
	i = 0
	j = 0

	length = len(char_hammingArray)
	while (i < length):
		if i in parity_positions:
			i += 1
			continue
		if char_bitarray[j]:
			char_hammingArray[i] = 1
		else:
			char_hammingArray[i] = 0
		i += 1
		j += 1

	#set each parity bit for the hamming code: 1 if checksum is odd, 0 if checksum is even
	for bit in parity_positions:
		#calculate the value of the check sum for the current parity bit

		check_sum = calc_checksum(char_hammingArray, bit)

		#if the checksum is odd, set the parity bit to 1, otherwise leave at 0
		if(check_sum%2!=0):
			char_hammingArray[bit] = 1
	char_hammingArray[-1] = 0

	total_parity = char_hammingArray.count(1)

	if(total_parity%2!=0):
		char_hammingArray[-1] = 1
	return char_hammingArray

'''
Convert 1s and 0s to A,T,C,G with following pattern:
A,T: 0
C,G: 1
bits alternate A,T/C,G to allow for more structurally sound DNA and minor error checking against indels
INPUT: bit array for hamming encoded character
OUTPUT: string of DNA for hamming encoded character
'''
def convert_char_bitarray(char_bitArray):
	#loop through each bit of the hamming code array
	zero_ind = 0
	one_ind = 0
	dna_out = ''
	for bit in char_bitArray:
		if bit!=0:
			if one_ind == 1:
				dna_out += 'C'
				one_ind = 0
			else:
				dna_out += 'G'
				one_ind = 1
		else:
			if zero_ind == 1:
				dna_out += 'A'
				zero_ind = 0
			else:
				dna_out += 'T'
				zero_ind = 1
	return dna_out

'''
INPUT: string of length 12 of DNA characters
OUTPUT: bitarray matching input characters, or, if an invalid character is found, None is returned
'''
def dna_to_bitarray(dna):
	char_list = list(dna)
	char_bitarray = bitarray(char_length+len(parity_positions))
	i=0
	for char in char_list:
		if char == 'A' or char == 'T':
			char_bitarray[i]=0
		elif char == 'C' or char == 'G':
			char_bitarray[i]=1
		else:
			print "Invalid character '",char,"' present in DNA sequence."
			return None
		i+=1
	return char_bitarray

'''
INPUT:
	char_bitarray: bit array of length 12 containing channel encoded character
	parity_positions: array of 0 indexed positions of parity bits in char_bitarray
OUTPUT:
	A tuple of formation (boolean, integer array) where boolean indicates if the bitarray passes all checksums
	and integer array contains the position of all invalid parity bits
'''
def validate_parity(char_bitarray):
	invalid_parity_bits = []
	valid = True
	for bit in parity_positions[:-1]:
		checksum = calc_checksum(char_bitarray, bit)
		#parity bit is 0 so checksum should be even
		if checksum%2!=0:
			invalid_parity_bits.append(bit)
			valid = False

	#sum over all elements preceding final parity check bit
	checksum = sum(char_bitarray)
	#if the total checksum isn't even, then the final parity bit is invalidated
	if(checksum%2!=0):
		valid = False
		invalid_parity_bits.append(len(char_bitarray)-1)
	return (valid, invalid_parity_bits)

'''
Given a sequence of DNA, return true if the order of characters alternates
return false if the order does not alternate appropriately
'''
def validate_char_order(dna):
	char_list = list(dna)
	AT_ind = 1
	CG_ind = 1
	for char in char_list:
		if char == 'A':
			if AT_ind == 1:
				return False
			AT_ind = 1
		elif char == 'T':
			if AT_ind == 0:
				return False
			AT_ind = 0
		elif char == 'C':
			if CG_ind == 1:
				return False
			CG_ind = 1
		elif char == 'G':
			if CG_ind == 0:
				return False
			CG_ind = 0
	return True

'''
INPUT:
	dna: DNA chunk encoding for hamming encoded data
OUTPUT:
	(RESULT, INDICES)
	RESULT: True/False; this chunk passes all parity
	INDICES: Indices of incorrect bits in the Hamming array
'''
def check_char(dna):
	char_bitarray = dna_to_bitarray(dna)
	parity_result = validate_parity(char_bitarray)
	order_result = validate_char_order(dna)

	#if a checksum did not pass or invalid order was found, return False
	if not parity_result[0] or not order_result:
		return (False, parity_result[1])
	return (True, None)

def round_down(num, divisor):
	return num - (num%divisor)


'''
INPUT:
	char_bitarray: bit array of hamming code
	invalid_bits: list of invalid parity bits
OUTPUT: corrected bit array
'''
def fix_hamming_chunk(char_bitarray, invalid_bits):
	#check if the final check bit is included. If it is, store it and remove it

	final_parity = None
	if len(char_bitarray)-1 in invalid_bits:
		final_parity = len(char_bitarray)-1
		invalid_bits.remove(final_parity)

	if len(invalid_bits) != 0:
		#sum the indexes that aren't the final check bit
		sum_indexes = -1
		for index in invalid_bits:
			#account for 0 base indexing
			sum_indexes += index+1


		#if the sum exceeds the length, this is a double error, so return the array unchanged to flag a double-error

		if sum_indexes > len(char_bitarray)-1:
			return char_bitarray

		if(char_bitarray[sum_indexes] == 1):
			char_bitarray[sum_indexes] = 0
		else:
			char_bitarray[sum_indexes] = 1

	if final_parity is not None:
		checksum = sum(char_bitarray[:-1])
		#if the checksum is even
		if checksum%2==0:
			char_bitarray[-1] = 0
		else:
			char_bitarray[-1] = 1

	return char_bitarray

'''
INPUT:
	chunk: a string of DNA for a hamming encoded character
OUTPUT: a bit array for the character encoded for
'''
def extract_valid_char(bitArray):
	char_array = BitArray('int:8=0')

	j = 0
	for i in range(0,12):
		if not i in parity_positions:
			char_array[j] = bitArray[i]
			j+=1
	return char_array

'''
INPUT:
	dna: full dna string
	start_ind: the index of the string at which to begin
	step: how large a hamming code chunk is
	parity_positions: zero indexed parity bit positions
OUTPUT: the number of
'''
def check_following(dna, start_ind, step):
	dna = dna[start_ind:]
	length = step*10
	#if the length is longer than the DNA string, reduce the length to the nearest multiple of the step size
	if length > len(dna):
		length = round_down(len(dna), step)

	chunks = [dna[i:i+step] for i in range(0, length, step)]
	i = 0
	valid=0
	for chunk in chunks:
		if i == 10:
			break
		if(check_char(chunk)):
			valid +=1
		i+=1
	return float(valid)/float(i+1)

def print_percentage(percent):
	sys.stdout.write("\rPercent Complete: %f%%" % percent)
	sys.stdout.flush()

'''
INPUT: an integer that was decoded in binary format
OUTPUT: Boolean indicating if this integer is a valid ascii character
'''
def check_ascii(ascii_int):
	if (ascii_int <= 127) and (ascii_int >= 0):
		return True
	return False

'''
INPUT:
	input_text: a block of text to be encoded by this worker process
	index: an integer representing what position this block of text is in the original content

OUTPUT: (encoded seq, index): The input text encoded in nucleotide bases and the input index
'''
def encode_worker(input_text, index):
	input_list = list(input_text)
	seq_out = ''

	#for every character in the input list, make a bit array for it encoded with the hamming code
	total_len = len(input_list)
	for character in input_list:
		char_hammingArray = set_hammingArray(character)
		char_string = convert_char_bitarray(char_hammingArray)

		seq_out += char_string
		#this is not thread safe but it's only being used for the percentage counter
		total_chars.value+=1
	return (seq_out, index)

'''
INPUT:
	chunks: array of text blocks the size of an encoded sequence
	index: the position in the original input this worker is processing

OUTPUT: (chunks decoded back to ASCII characters, input index, (the number of characters fixed with a single error, a double error))
'''
def decode_worker(chunks, index):
	decoded_chunks = ''
	num_single_fixes = 0
	num_double_fixes = 0
	for chunk in chunks:
		dna_bitarray = dna_to_bitarray(chunk)
		valid_tuple = check_char(chunk)
		valid = valid_tuple[0]
		output_char = ''
		if not valid:
			valid_hamming_array = fix_hamming_chunk(dna_bitarray, valid_tuple[1])
			parity_validation = validate_parity(valid_hamming_array)
			if not parity_validation[0]:
				output_char = '?'

				num_double_fixes += 1
			else:
				valid_char_array = extract_valid_char(valid_hamming_array)
				ascii_int = int(valid_char_array.bin, 2)
				if(check_ascii(ascii_int)):
					output_char = str(unichr(ascii_int))
					num_single_fixes += 1
				else:
					output_char = '?'
					num_double_fixes += 1

			decoded_chunks += output_char
		else:
			valid_char_array = extract_valid_char(dna_bitarray)
			ascii_int = int(valid_char_array.bin, 2)
			if(check_ascii(ascii_int)):
				output_char = str(unichr(ascii_int))
			else:
				output_char = '?'
				num_double_fixes += 1
			decoded_chunks += output_char
		#this is not thread safe but it's only being used for the percentage counter
		total_chars.value+=1
	return (decoded_chunks, index, (num_single_fixes, num_double_fixes))


def percent_tab(total_num):
	while total_num!=total_chars:
		print_percentage((float(total_chars.value)/float(total_num))*100)
		time.sleep(0.1)

'''
INPUT:
	output_array [(content_block, indice),...]: Array containing content to be written, broken into blocks contained in
	tuples, paired with their intended index
	num_workers: the number of workers that prepared the output_array (should match the length of output_array)
	output_file_object: file handle to write to
	max_line: Either an integer, or None. If None, ignore. If integer, place newline every n characters
OUTPUT:
	None. Writes contents to output_file_object


'''
def write_output(output_array, num_workers, output_file_object, max_line):
	ordered_results = [None]*num_workers
	for output in output_array:
		ordered_results[output[1]] = output[0]

	if not max_line:
		for output in ordered_results:
			output_file_object.write(output)
	else:
		total_text = ''
		for output in ordered_results:
			total_text += output
		total_text = '\n'.join(total_text[i:i+max_line] for i in range(0, len(total_text), max_line))
		output_file_object.write(total_text)

'''
INPUT:
	base: a random nucleotide
OUTPUT: A randomly selected nucleotide NOT equal to input
'''
def mutate(base):
	bases = ["A", "T", "C", "G"]
	if base not in bases:
		print "Base '"+base+"' not a valid base."
		return None
	mutation = random.sample(bases,1)[0]
	while mutation == base:
		mutation = random.sample(bases,1)[0]
	return mutation

def main(argv):
	inputfile = ''
	outputfile = ''
	#set up and parse command line arguments. Handle errors if arguments not provided properly
	parser = argparse.ArgumentParser(add_help=True)
	parser.add_argument("input")
	parser.add_argument("output", nargs='?', default='out.txt')
	parser.add_argument('--decode', '-d', action='store_true', help='decode boolean flag')
	parser.add_argument('--encode', '-e', action='store_true', help='encode boolean flag')
	parser.add_argument('--corrupt', '-c', action='store_true', help='data corruption flag')
	parser.add_argument('--workers','-w', action="store", dest="w", type=int, help='number of processes to spawn', default='1')
	parser.add_argument('--error_rate','-r', action="store", dest="r", type=int, help='define error rate as 1 error per r characters (bigger values for smaller error rates)', default='1000')
	args = parser.parse_args()
	if((not args.decode) and (not args.encode) and (not args.corrupt)):
		print "usage: convert.py [-h] [--decode] [--encode] [--corrupt] input [output]"
		print "convert.py: error: must specify --decode, --encode or --corrupt flag"
		sys.exit(2)
	if((args.decode and args.encode) or (args.corrupt and args.encode) or (args.corrupt and args.decode)):
		print "usage: convert.py [-h] [--decode] [--encode] input [output]"
		print "convert.py: error: must specify either --decode, --encode or --corrupt flag, not multiple"
		sys.exit(2)
	print "Reading input and output files..."
	inputfile = args.input
	outputfile = args.output
	num_workers = args.w
	if num_workers == 0:
		print "convert.py: error: number of workers cannot be 0. Default is 1"
		sys.exit(2)

	#open file descriptors of inptut and output files
	input_file_object = open(inputfile, 'r')
	output_file_object = open(outputfile, 'w')

	#convert input file to a string and then split into a list of characters
	input_text = input_file_object.read()

	print "Input File: ",inputfile
	print "Output File: ",outputfile

	#define an array of positions for parity bits
	parity_bit = 1
	while parity_bit <= char_length+len(parity_positions):
		parity_positions.append(parity_bit-1)
		parity_bit *= 2
	parity_positions.append(char_length+len(parity_positions))

	#define an array to hold the input for different workers, one indice per worker
	worker_input = [None]*num_workers

	#if the command is for encoding
	if args.encode:
		#calculate the maximum length of a data-chunk to be sent to a worker process
		input_len = int(math.ceil(float(len(input_text))/float(num_workers)))
		#divide the input text up and place it into an array, one entry for each worker
		for i in range(0,num_workers):
			worker_input[i] = input_text[(i*input_len):((i*input_len)+input_len)]

		print "Encoding to Hamming Channel Code..."

		#create a process pool
		pool = mp.Pool(processes=num_workers)
		#call the encode_worker function with the appropriate
		results = [pool.apply_async(encode_worker, args=(worker_input[i],i)) for i in range(0,len(worker_input))]

		perc_proc = mp.Process(target=percent_tab, args=(len(input_text),))
		perc_proc.start()
		output_segs = [p.get() for p in results]
		#when we get this far, terminate the percent tallying processes
		perc_proc.terminate()
		output_file_object.write('>Hamming Code Output: '+outputfile+', Characters Encoded: '+str(len(input_text))+'\n')
		#order the output and write to output file
		write_output(output_segs, num_workers, output_file_object, 80)

		print "\nSuccessfully converted"
	elif args.decode or args.corrupt:
		print "Parsing FASTA file format"

		header = input_text.split('\n', 1)[0]
		if header[0] != ">":
			print "Input file not valid FASTA format"
			sys.exit(2)
		print "FASTA Header: "
		print header,"\n"
		#get the content after the header line and remove all instances of new lines
		dna = input_text.split('\n', 1)[1]
		dna = dna.replace("\n", "")
		if args.decode:
			print "Decoding from Hamming Channel Code..."
			step = char_length+len(parity_positions)
			chunks = [dna[i:i+step] for i in range(0, len(dna), step)]

			input_len = int(math.ceil(float(len(chunks))/float(num_workers)))
			for i in range(0,num_workers):
				worker_input[i] = chunks[i*input_len:(i*input_len+input_len)]

			pool = mp.Pool(processes=num_workers)
			results = [pool.apply_async(decode_worker, args=(worker_input[i],i)) for i in range(0,len(worker_input))]

			perc_proc = mp.Process(target=percent_tab, args=(len(dna)/len(chunks[0]),))
			perc_proc.start()
			output_segs = [p.get() for p in results]

			num_singles = 0
			num_doubles = 0
			for seg in output_segs:
				num_singles += seg[2][0]
				num_doubles += seg[2][1]


			#when we get this far, terminate the percent tallying processes
			perc_proc.terminate()
			#order the output and write to output file
			write_output(output_segs, num_workers, output_file_object, False)

			print "\nSuccessfully decoded."
			print str(num_singles)+" single errors detected and fixed."
			print str(num_doubles)+" double errors detected."

		#if data is to be corrupted
		else:
			random.seed()
			print "Randomly mutating data at rate of 1 error per "+str(args.r)+" bases."
			#create list of DNA bases
			base_list = list(dna)
			rate = 1.0/float(args.r)
			num_mutations = int(len(base_list)*rate)
			index_list = []
			for i in range(0,num_mutations):
				print_percentage((float(i)/float(num_mutations))*100)
				index = int(random.random()*len(base_list))
				index_list.append(index)
				base_list[index] = mutate(base_list[index])

			index_list = sorted(index_list)
			#find out how many of the mutations might cause double mutations (no guarantee they're in the same hamming chunk)
			num_double = 0
			for i in range(1,len(index_list)-1):
				if index_list[i]-index_list[i-1] < 13:
					num_double += 1
				if index_list[i+1] - index_list[i] < 13:
					num_double +1

			dna = ''.join(base_list)
			print "\nWriting output file"
			output_file_object.write(header+'\n')
			write_output([(dna,0)], 1, output_file_object, 80)
			print "Complete: "+str(num_mutations)+" mutations inserted. \n"+str(num_double)+" possible double mutations. \nMinimum index: "+str(index_list[0])+" Maximum index: "+str(index_list[-1])

	else:
		print "No --encode or --decode flags set"
		sys.exit(2)
	#close the open input and output files
	output_file_object.close()
	input_file_object.close()

if __name__ == "__main__":
	main(sys.argv[1:])
