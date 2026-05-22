find_holdings_snp
pl
Michael Sinkinson shared this file. Want to do more with it?
#!/usr/bin/perl -s
use List::Util qw(max);
use List::Util qw(sum);
use List::Util qw(min);
use Math::Round;
﻿
#######################################
# find_holdings_snp.pl
# Michael Sinkinson
# October 2018
#######################################
﻿
#######################################
# Description:
# Extracts 13(f) holding information from filings.
# Main function of interest is "ReadThis()", which takes as an argument a path to a filing. Rest is mostly a wrapper. 
# $processnum is a simple way to run this in parallel: each process gets different years of filings to go over.
# To run from command line: perl find_holdings_snp.pl
# When prompted, enter a process number (1-12), or 13 to combine the output from all other processes. 
# To run in parallel, at the command line: start perl find_holdings_snp.pl
# This opens a new window. Open 12 and set them running on the different processes. Then run 13 to combine output. (on a 12+ core machine)
#
# INPUTS: 
# - snp_quarter.csv: "quarter" is actually the reporting date, e.g. 20010331. 
# --- This file should have one line, a pipe-separated (|) list of CUSIP codes that you are interested in. 
# - colswap_list.txt: a manual list of files where the columns are known to be in the wrong order. 
# - crsp_price_out.csv: Data from CRSP on the closing price and shares outstanding. 
# --- Six columns: year, month, day, CUSIP, price, shares outstanding. 
# --- Note that the CRSP monthly update gives you the last trading day of the month; replace with the actual last day of the quarter (e.g. if March 30 is Friday, the last trading day, change that record to March 31). 
# - The SEC 13f filings, which are assumed to be stored in a mirror way to the SEC EDGAR database, and organized by filing date (e.g. f2002 is all filings from 2002, etc).
#
# OUTPUTS: 
# - out_process.txt / out_all.txt: the holdings. Columns are: cik, reportingdate, filingdate, filingtype, cusip, shares, validation, sole, shared, none
# - cik_map_process.txt / _all.txt: mapping from CIK to CIKNAME at the quarter level. 
# - err_process.txt / _all.txt: error log
# - errsusp_process.txt / _all.txt: log of 'suspicious holdings', e.g. > 50% of shares outstanding. 
# - log_process.txt / _all.txt: extremely verbose log of the parsing process. Basically every line of a filing with a CUSIP. 
#
#######################################
﻿
# BEGIN
﻿
print "What process?\n"; # Enter 1-12 for different years, or 13 to combine output from prior processes. 
﻿
my $processnum = <STDIN>;
chomp $processnum;
﻿
# This code is written for my desktop machine with full text filings. 
﻿
# List of quarters:
my @qlist = ('19981231', '19990331', '19990630', '19990930', '19991231', '20000331', '20000630', '20000930', '20001231', '20010331', '20010630', '20010930', '20011231', '20020331', '20020630', '20020930', '20021231', '20030331', '20030630', '20030930', '20031231', '20040331', '20040630', '20040930', '20041231', '20050331', '20050630', '20050930', '20051231', '20060331', '20060630', '20060930', '20061231', '20070331', '20070630', '20070930', '20071231', '20080331', '20080630', '20080930', '20081231', '20090331', '20090630', '20090930', '20091231', '20100331', '20100630', '20100930', '20101231', '20110331', '20110630', '20110930', '20111231', '20120331', '20120630', '20120930', '20121231', '20130331', '20130630', '20130930', '20131231', '20140331', '20140630', '20140930', '20141231', '20150331', '20150630', '20150930', '20151231', '20160331', '20160630', '20160930', '20161231', '20170331', '20170630', '20170930', '20171231', );
# List of CUSIPs for each quarter:
my %targets = ();
foreach $q (@qlist) {
	open(INQ, "snp_$q.csv");
	my $line = <INQ>;
	chomp $line;
	$targets{$q} = uc $line;
	close(INQ);
}
﻿
# Manual list of files that have the column order reversed. 
my %filefix = ();
if (-e 'colswap_list.txt'){ 
	# we have a list of files that present troublesome files (where value is after shares)
	open(COLS, 'colswap_list.txt');
	while ($line = <COLS>) {
		chomp $line;
		($ff, $sc, $c, $notes) = split /\t/, $line;
		if ($c ==1) {
			$filefix{$ff} = 1;
			print "Will swap columns for $ff\n";
		}
	}
	close(COLS);
﻿
}
﻿
# Import CRSP price and share data. 
my %validation = ();
open(IN, '< crsp_price_out.csv');
$line = <IN>;
while ($line = <IN>) {
	chomp $line;
	($y, $m, $d, $cusip, $prc, $shrout) = split /,/, $line;
	if($prc>0) {
		if (($m==3)|($m==6)|($m==9)|($m==12)) {
			$thisdate = $y*10000 + $m*100 + $d; # convert y, m, d to YYYYMMDD format.
			$validation{$thisdate}{$cusip}{'prc'} = $prc;
			$validation{$thisdate}{$cusip}{'shrout'} = $shrout;
		}
	}
}
close(IN);
﻿
# Data storage hashes. 
my %outdata = (); # Main output hash. 
my %valuedata = (); # Auxiliary output hash (value)
my %val = (); # Validation hash
my %cikmap = (); # mapping from cik to cikname
my %va = (); # voting authority data
﻿
# The plan is for this code to walk through a set of filings. 
my @flist = (); # List of folders to crawl
my $fileext = ''; # This process' file extension to use for logs and output.
﻿
# Files are stored in folgers based on filing date, e.g. f2001, f2002, etc. 
# Full list: my @flist= ('f1999', 'f2000', 'f2001', 'f2002', 'f2003', 'f2004', 'f2005', 'f2006', 'f2007', 'f2008', 'f2009', 'f2010', 'f2011', 'f2012', 'f2013', 'f2014', 'f2015', 'f2016', 'f2017');
if ($processnum == 1) {
print "Process 1\n";
@flist= ('f1999', 'f2000', 'f2001', 'f2002');
$fileext = '_1';
} elsif ($processnum == 2) {
@flist= ('f2003', 'f2004');
$fileext = '_2';
} elsif ($processnum == 3) {
@flist= ('f2005', 'f2006');
$fileext = '_3';
} elsif ($processnum == 4) {
@flist= ('f2007', 'f2008');
$fileext = '_4';
} elsif ($processnum == 5) {
@flist= ('f2009', 'f2010');
$fileext = '_5';
} elsif ($processnum == 6) {
@flist= ('f2011');
$fileext = '_6';
} elsif ($processnum == 7) {
@flist= ('f2012');
$fileext = '_7';
} elsif ($processnum == 8) {
@flist= ('f2013');
$fileext = '_8';
} elsif ($processnum == 9) {
@flist= ('f2014');
$fileext = '_9';
} elsif ($processnum == 10) {
@flist = ('f2015');
$fileext = '_10';
} elsif ($processnum == 11) {
@flist = ('f2016');
$fileext = '_11';
} elsif ($processnum == 12) {
@flist = ('f2017');
$fileext = '_12';
} elsif ($processnum == 13) {
	# Combine all of the process outputs
	open(OUT, "> out_all.txt");
	open(ERR, "> err_all.txt");
	open(CIKMAP, "> cik_map_all.txt");	
	print OUT "cik\trdate\tfdate\tfiletype\tcusip\tshares\tval\tsole\tshared\tnone\n";
	foreach $n (1..12) {
		open(IN, "< out__$n.txt");
		$line = <IN>;
		while ($line = <IN>) {
			print OUT "$line\t\t\t";
		}
		close(IN);
		open(IN, "< err__$n.txt");
		$line = <IN>;
		while ($line = <IN>) {
			print ERR $line;
		}
		close(IN);		
		open(IN, "< cik_map__$n.txt");
		$line = <IN>;
		while ($line = <IN>) {
			print CIKMAP $line;
		}
		close(IN);		
	}
	close(OUT);
	close(ERR);
	close(CIKMAP);
	die "Complete.\n";
} else {
die "Invalid process number\n";
}
﻿
# Log files for parsing. 
open(ERR, "> err_$fileext.txt");
open(ERRSUSP, "> errsusp_$fileext.txt");
﻿
﻿
#### PRIMARY WRAPPER
### Go through each folder that I am assigned to, find filings, pass them to ReadThis(). 
﻿
foreach $fol (@flist) {
	open(LOG, "> log_$fol.txt");
	$basedir = 'C:\wrds_13f\\' . $fol;
	opendir(DIR1, $basedir) or die "Unable to open $basedir:$!\n";
	my @names1 = readdir(DIR1) or die "Unable to read $basedir:$!\n";
	closedir(DIR1);
	foreach my $name1 (@names1){
		next if ($name1 eq "."); 
		next if ($name1 eq "..");
		my $subdir = $basedir . '\\' . $name1;
		opendir(DIR2, $subdir);
		my @names2 = readdir(DIR2);
		closedir(DIR2);
		foreach my $name2 (@names2) {
			#these folders are firms
			next if ($name2 eq "."); 
			next if ($name2 eq "..");			
			my $codir = $subdir . '\\' . $name2;
			print "$codir\n";
			opendir(DIR3, $codir);
			my @names3 = readdir(DIR3);
			closedir(DIR3);
			foreach my $filing (@names3) {
				if ($filing =~ /\.txt/) {
				# found a text file
					my $fn = $codir . '\\' . $filing;
					ReadThis($fn);
				}
			}
		}
	}
	close(LOG);
}
﻿
# Output results: 
﻿
open(OUTFILE, "> out_$fileext.txt");
print OUTFILE "cik\trdate\tfdate\tfiletype\tcusip\tshares\tval\tsole\tshared\tnone\n";
foreach my $c (sort keys %outdata) {
	foreach my $d (sort keys %{$outdata{$c}}) {
		foreach my $fd (sort keys %{$outdata{$c}{$d}}) {
			foreach my $t (sort keys %{$outdata{$c}{$d}{$fd}}) {
				foreach my $tt (sort keys %{$outdata{$c}{$d}{$fd}{$t}}) {
					print OUTFILE "$c\t$d\t$fd\t$t\t$tt\t$outdata{$c}{$d}{$fd}{$t}{$tt}\t$val{$c}{$d}{$fd}{$t}{$tt}";
					print OUTFILE "\t".$va{$c}{$d}{$fd}{$t}{$tt}{'sole'};
					print OUTFILE "\t".$va{$c}{$d}{$fd}{$t}{$tt}{'shared'};
					print OUTFILE "\t".$va{$c}{$d}{$fd}{$t}{$tt}{'none'};										
					print OUTFILE "\n";
				}		
			}
		}	
	}
}
close(OUTFILE);
open(OUTFILE, "> cik_map_$fileext.txt");
foreach my $c (sort keys %cikmap) {
	foreach my $m (sort keys %{$cikmap{$c}}) {
		foreach my $d (sort keys %{$cikmap{$c}{$m}}) {
			print OUTFILE "$c\t$m\t$d\n";
		}	
	}
}
close(OUTFILE);
close(ERR);
close(ERRSUSP);
﻿
﻿
### END MAINLINE
﻿
### FUNCTIONS
﻿
sub ReadThis {
	# This function takes a file path as an input, and extracts holdings for the desired CUSIPs. 
	$thisf = shift;
	# Open and read file. 
	open(FH, $thisf);
	@lines = <FH>;
	@lines = map{uc($_)} @lines;
	$alltext = join //, @lines;	
	$alltarget = 'x1x1x1x1x1x1x11x1x1x1x1x1'; # initialize the target string with junk (will be |-separated CUSIPs)
	close(FH);
	my %susp = (); # "Suspicious" holdings
	my $suspnum = 1; # How many suspicious holdings in this file; if high, be worried the format is strange. 
	# Parse the header to get filing date, reporting date, CIK of reporter and CIKNAME. 
	if ($alltext =~ /CONFORMED PERIOD OF REPORT:\s+(\d+)/) {
		$thisdate = $1;
		# Based on the reporting date, get the list of target CUSIPs we are looking for: 
		if (exists $targets{$thisdate}) {
			$alltarget = $targets{$thisdate};	
			@alltargetlist = split /\|/, $alltarget;
		} else {	
			if ($alltext =~ /FILED AS OF DATE:\s+(\d+)/) {
				$thisfdate = $1;
				@lesslist = grep($_ < $thisfdate, @qlist);
				$thisdate = max(@lesslist);
				$alltarget = $targets{$thisdate};	
				@alltargetlist = split /\|/, $alltarget;
			} else {
				# Can't find the filing date; don't know what to look for. 
				print "CANNOT PROCESS $thisf\n";
				print ERR "CANNOT PROCESS $thisf\n";
			}			
		}
	} else {
		# This filing doesn't seem to have a header. 
		print "CANNOT find date for $thisf\n";
		print ERR "CANNOT find date for $thisf\n";
	}
	# Parse the files (except for 1998 filings)
	if ($thisdate ne '19981231') {
		# Handle XML files separately:
		if ($alltext =~ /<XML>/) {
			# XML files are easier. Need CIK, Type, Name, Dates
			print LOG "Found an XML file $thisf \n";
			$thisfdate = "MISSING";
			if ($alltext =~ /FILED AS OF DATE:\s+(\d+)/) {
				$thisfdate = $1;
			}
			$thiscik = "MISSING";
			if ($thisf =~ /\\(\d+)\\[\d\-]+\.txt/) {
			$thiscik = $1;
			}		
			if ($alltext =~ /<TYPE>(.*?)\n/) {
				$thistype = $1;		
			} else { 
				$thistype = "MISSING";
			}
			if ($alltext =~ /COMPANY CONFORMED NAME:\s+(.*?)\n/) {
				$thismgr = $1;
			} elsif ($alltext =~ /\nNAME:\s+(.*?)\n/) {
				$thismgr = $1;		
			} else { 
				$thismgr = "MISSING";
			}
			$cikmap{$thiscik}{$thismgr}{$thisdate} = 1; # record CIKNAME
			print LOG "Name: $thismgr\nCIK: $thiscik\nType: $thistype\nDate: $thisdate\n";		
			# Flatten the file and extract out each infoTable entry. 
			$alltext =~ s/\n//g;
			$alltext =~ s/\t//g;
			my @stockentries = ($alltext =~ /INFOTABLE>(.*?)<\/[^>]*INFOTABLE>/g);
			my @targetlines = grep /CUSIP>\s*($alltarget)\s*\d?<\//, @stockentries; # every  infoTable containing a CUSIP we want. 
			# filter out put/call/options/warrangs
			@targetlines = grep(!/PUTCALL>(PUT|CALL)<\//, @targetlines);
			@targetlines = grep(!/SSHPRNAMTTYPE>\h*(PRN)\h*<\//, @targetlines);
			@targetlines = grep(!/TITLEOFCLASS>.*?(\bPUT\b|\bCALL\b|\bOPT|\bWAR).*?<\//, @targetlines);
			# Go over each holding:
			foreach $t (@targetlines) {
				print LOG "$t\n";
				if ($t =~ /($alltarget)/i) {
					$thistarget = $1; # CUSIP of current entry
					$temp = 0; # This will hold the "Guess" of the number of shares to be confirmed. 
					$sole = 0; # Initialize SOLE voting shares
					$shared = 0; # Initialize SHARED voting shares
					$none = 0; # Initialize NONE voting shares
					# Make sure CRSP validation exists: 
					if (exists $validation{$thisdate}{$thistarget}{'shrout'}) {
						$thisshrout = $validation{$thisdate}{$thistarget}{'shrout'}; # This CUSIP's shares outstanding
						$thisprc = $validation{$thisdate}{$thistarget}{'prc'}; # This CUSIP's price at the reporting date
						if ($t =~ /SSHPRNAMT>\h*([\d\.,]+)\h*<\//) {
							# Extract number of shares, remove comma
							$temp = $1;
							$temp =~ s/,//g;
							if ($temp > 0) {
								$thisvalue = 0; # The reported "value"
								if ($t =~ /VALUE>\h*([\d\.,]+)\h*<\//) {
									$thisvalue = $1;								
								}
								# For valuation: let's check if price * shares == value (or is at least close). 
								$thisratio = 0;
								$thisaltratio = 0;
								$thisval = 0;								
								$thisdenom = round($temp*$thisprc/1000);
								$thisaltdenom = round($temp*$thisprc);
								$thisratio = ($thisvalue / $thisdenom) if $thisdenom;
								$thisaltratio = ($thisvalue / $thisaltdenom) if $thisaltdenom;
								if ((abs($thisratio-1) < 0.1)||(abs($thisaltratio-1) < 0.1)){
									$thisval = 1; # Validated! 
								}
								if ($thisval == 0) {print "$thisvalue\t$temp\t$thisprc\t$thisval\t$thisratio\n";}
								$outdata{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget} = $temp + $outdata{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget};
								$val{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget} = $thisval;
							}
						} else {
							# This should never occur in XML format. 
							print "Cannot find shares: $t\n";
							print ERR "Cannot find shares: $t\n";
						}
						# Extract the SOLE/SHARED/NONE values. 
						if ($t =~ /SOLE>\h*([\d\.,]+)\h*<\//) {
							$sole = $1;
							$va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'sole'} = $sole +$va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'sole'} ;
						}
						if ($t =~ /SHARED>\h*([\d\.,]+)\h*<\//) {
							$shared = $1;
							$va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'shared'} = $shared + $va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'shared'} ;
						}
						if ($t =~ /NONE>\h*([\d\.,]+)\h*<\//) {
							$none = $1;
							$va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'none'} = $none +$va{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget}{'none'} ;
						}		
					}
				} else { 
					print "Cannot find CUSIP: $t\n";
					print ERR "Cannot find CUSIP: $t\n";
				}
			}		
			close(FH); 
		} elsif ($alltext =~ /$alltarget/) {
			# Non XML filings: make sure one of the target CUSIP appears. 
			print LOG "Found a file with holdings $thisf \n";
			$thisfdate = "MISSING";			
			if ($alltext =~ /FILED AS OF DATE:\s+(\d+)/) {
				$thisfdate = $1;
			}
			$thiscik = "MISSING";
			if ($thisf =~ /\\(\d+)\\[\d\-]+\.txt/) {
			$thiscik = $1;
			}
			if ($alltext =~ /<TYPE>(.*?)\n/) {
				$thistype = $1;		
			} else { 
				$thistype = "MISSING";
			}
			if ($alltext =~ /COMPANY CONFORMED NAME:\h+(.*?)\n/) {
				$thismgr = $1;
			} elsif ($alltext =~ /\nNAME:\s+(.*?)\n/) {
				$thismgr = $1;		
			} else { 
				$thismgr = "MISSING";
			}
			$thisff = $filefix{$thisf}; # Is this file known to have columns reversed? 
			if ($thiscik == 918509) {
				if ($thisdate < 20050101) {
					$thisff = 1;
					# darn dutch pensions...
				}
			}
			$cikmap{$thiscik}{$thismgr}{$thisdate} = 1; # track CIKNAME
			print LOG "Name: $thismgr\nCIK: $thiscik\nType: $thistype\nDate: $thisdate\n";
			# Pull out lines of text that contain a CUSIP we are looking for. This line is super costly for execution time: 
			@targetlines = grep /$alltarget/i, @lines;
			# Remove derivatives using word bounds
			@targetlines = grep(!/\bPUT\b/, @targetlines);
			@targetlines = grep(!/\bCALL\b/, @targetlines);
			@targetlines = grep(!/\bCONV BD\b/, @targetlines);
			@targetlines = grep(!/\bCONV BOND\b/, @targetlines);
			@targetlines = grep(!/\bOPT\b/, @targetlines);
			# Cycle through each line that has a target CUSIP
			foreach $t (@targetlines) {
				$t =~ s/\"//g; # Remove quotes. 
				# Remove stock prices, which are sometimes included for some reason. 
				$t =~ s/\b\d{1,2}\.\d{2}\b/ /;
				print LOG "$t";
				$t =~ /($alltarget)/;
				$thistarget = $1; # This line's CUSIP
				if (exists $validation{$thisdate}{$thistarget}{'shrout'}) {
					$tempv = 0; # Will be "value"
					$temps = 0; # Will be "shares"
					# Attempt to pattern match to find # shares:
					if ($t =~ /$thistarget\d(\d{2,})\s+([\d\.,]+)\s*SH/) {
					# babson's filings are messed up... 
						$temps = $2;
						$tempv = $1;
					} elsif ($t =~ /$thistarget\d?,(\d+),(\d+)/) {
					# argyle and cortland loves commas
						$temps = $2;
						$tempv = $1;
					} elsif ($t =~ /$thistarget\d?\s+([\d\.,]+)\s+([\d\.,]+)\s*?SH/) {
						$temps = $2;
						$tempv = $1;
					} elsif ($t =~ /([\d\.,]+)\s+([\d\.,]+)\s*?SH/) {
						$temps = $2;
						$tempv = $1;
					} elsif ($t =~ /$thistarget\s+([\d,\.])+\s+([\d,\.]+)\s/) {
						$temps = $2;
						$tempv = $1;
					} elsif ($t =~ /$thistarget\d\s+([\d,\.])+\s+([\d,\.]+)\s/) {
						$temps = $2;
						$tempv = $1;
					}  elsif ($t =~ /$thistarget\d?\s+([\d,\.])+\s+SH\s+([\d,\.]+)\s/) {
						$temps = $2;
						$tempv = $1;
					}
					# Validation and cleaning: sometimes column separators are missing. Attempt to fix. Use commas to help (as digits tend to be in groups of 3 near commas)
					if ($temps =~ /,\d{4,6},/) {
						$temps =~ s/,(\d{3})(\d{1,3}),/,$1 $2,/;
						$temps =~ s/,//g;
						$temps =~ /(\d+)\s+(\d+)$/;
						$temps = $2;
						$tempv = $1;						
					}
					if ($temps =~ /\d{3},\d{1,2},\d{3}/) {
						$temps =~ s/(\d{3}),(\d{1,2}),(\d{3})/$1 $2,$3/;
						$temps =~ s/,//g;
						$temps =~ /(\d+)\s+(\d+)$/;
						$temps = $2;	
						$tempv = $1;
					}					
					if ($temps =~ /,\d$/) {
						$temps =~ s/,\d$//;
						$temps =~ s/,//g;
						$temps =~ /(\d+)$/;
						$temps = $1;						
					}										
					# Finally remove commas. 
					$temps =~ s/,//g;					
					$tempv =~ s/,//g;					
					# Common sense testing on num shares:
					$thisshrout = $validation{$thisdate}{$thistarget}{'shrout'};
					$thisprc = $validation{$thisdate}{$thistarget}{'prc'};
					if (($thisprc > 0)&($thisshrout > 0)) {
						if ($thisff  == 1) {
							# I have determined that this filing reports shares before value
							$temp = $tempv;
							$tempv = $temps;
							$temps = $temp;
						}
						# First check: did I accidentally extract price?
						if (abs(($temps/$thisprc)-1)<.1) {
							# I got price...  strip out price, re-process line
							$tback = $t;
							$t =~ s/\s$temps\s/\s/;
							$temps = 0;
							if ($t =~ /$thistarget\d?\s+([\d,\.])+\s+([\d,\.]+)\s/) {
								$tempv = $1;
								$temps = $2;
								$tempv =~ s/,//g;
								$temps =~ s/,//g;
								print ERR "Stripped out price ($thiscik, $thisdate, $temps, $thisshrout): $tback\n";
							}
						}
						# Check if this holding looks "suspicious", in that (price * shares) ~= value+/-25%
						if (($temps/($thisshrout*1000))>.25) {
							print ERR "Suspicious ($thiscik, $thisdate, $temps, $thisprc, $thisshrout): $t\n";
							$susp{$suspnum}{'record'} = $t;
							$susp{$suspnum}{'resolved'} = 0;
							# I am suspicious. Maybe captured value instead of shares; or shares smushed into value. 
							# Look for numbers at end of row; their sum should appear earlier in the row. 
							$t =~ s/,//g; # Remove commas from entire row of text. 
							# Many filings have the sole/shared/none at the end of the row, and they should add to the # shares. 
							if ($t =~ /^(.*?)\h*([\d\.]*\h*?[\d\.]*\h+[\d\.]+)$/) {
								# split the row to get the last three numbers. 
								$start = $1;
								$end = $2;
								@endnums = $end =~ /([\d\.]+)/g;
								$endsum = sum(@endnums);
								if (($start =~ /$endsum/)&(($endsum/($thisshrout*1000))<.25)&($endsum > 100)) {
									# replace
									print ERR "$t\nFirst try $temps, replacing with $endsum\n";
									print "$t\nFirst try $temps, replacing with $endsum\n";
									$temps = $endsum;		
									$susp{$suspnum}{'resolved'} = 1									
								}
								# Second try: look to split the number of shares into two numbers such that first ~= second*prc. This fixes (hopefully) when no column separator. 
								for $d (1..(length($temps)-1)) {
									$firstnum = substr $temps, 0, $d;
									$secondnum = substr $temps, $d;
									if (($secondnum * $thisprc  / 1000) > 0 ) {
										if (abs(($firstnum / ($secondnum * $thisprc / 1000))-1) < 0.05) {
											$temps = $secondnum;
											print ERR "HOORAY: it looks like $temps works\n";
											$susp{$suspnum}{'resolved'} = 1									
										}
									}
								}
							}
							print ERRSUSP "$thiscik\t$thisdate\t$temps\t$thisshrout\t$suspnum\t" . $susp{$suspnum}{'resolved'} . "\t" . $susp{$suspnum}{'record'} . "\n";
							$suspnum++;
						}
					}					
					$outdata{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget} = $temps + $outdata{$thiscik}{$thisdate}{$thisfdate}{$thistype}{$thistarget};			
				}				
			}	
		}
	}
}
We use cookies to provide, improve, protect and promote our services. Visit our Privacy Policy and Privacy Policy FAQs to learn more. You can manage your personal preferences, including your ‘Do not sell or share my personal data to third parties’ setting using the “Customize cookies” button below.