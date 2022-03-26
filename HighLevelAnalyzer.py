# High Level Analyzer
# For more information and documentation, please go to https://support.saleae.com/extensions/high-level-analyzer-extensions

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, NumberSetting, ChoicesSetting
import re

numberPatterns = {
    "0": "1101\d111",
    "1": "0101\d000",
    "2": "1011\d101",
    "3": "1111\d001",
    "4": "0111\d010",
    "5": "1110\d011",
    "6": "1110\d111",
    "7": "0101\d001",
    "8": "1111\d111",
    "9": "1111\d011",
    "L": "1000\d110",
    "": "0000\d000"
}
dotPattern = "\d{4}1\d{3}"

bitFlags = {
    "Voltage": 128,
    "Current": 129,
    "Resistance": 132,
    "Temperature": 134,
    "DC": 86,
    "AC": 87,
    "Exponent_Mega": 130,
    "Exponent_Kilo": 131,
    "Exponent_Milli": 126,
    "Exponent_Micro": 125,
    "Exponent_Secondary_Kilo": 73
}


# High level analyzers must subclass the HighLevelAnalyzer class.
class Hla(HighLevelAnalyzer):
    # List of settings that a user can set for this High Level Analyzer.

    # An optional list of types this analyzer produces, providing a way to customize the way frames are displayed in Logic 2.
    result_types = {
        "LCD": {
            "format": "{{data.parsed}}{{data.mode}}, {{data.parsed2}}"
        },
        "LCDError": {
            "format": "ERROR: {{data.error_info}}",
        }
    }

    def __init__(self):
        '''
        Initialize HLA.

        Settings can be accessed using the same name used above.
        '''
                # Holds the individual SPI result frames that make up the transaction
        self.frames = []

        # Whether SPI is currently enabled
        self.spi_enable = False

        # Start time of the transaction - equivalent to the start time of the "Enable" frame
        self.transaction_start_time = None

        # Whether there was an error.
        self.error = False

    def handle_enable(self, frame: AnalyzerFrame):
        self.frames = []
        self.spi_enable = True
        self.error = False
        self.transaction_start_time = frame.start_time

    def reset(self):
        self.frames = []
        self.spi_enable = False
        self.error = False
        self.transaction_start_time = None

    def is_valid_transaction(self) -> bool:
        return self.spi_enable and (not self.error) and (self.transaction_start_time is not None) and (len(self.frames) == 137)

    def handle_result(self, frame):
        if self.spi_enable:
            self.frames.append(frame)

    def get_frame_data(self) -> dict:
        outDigits = []
        outDigits2 = [] # ex. hz display in AC voltage mode at the top
        mode = ""
        overload = False
        parsed = 0.0 # voltage/current/ohms/centigrade
        parsed2 = 0.0 # frequency when in an ac mode

        # decode main digits, bit 9-17, 18-26, 27-35, 36-44
        for idx in range(3,-1, -1):
            #print("idx: " + str(idx))
            digit = bytes()
            for x in range(9+8*idx, 9+8*(idx+1)):
                #print("x: " + str(x))
                digit += self.frames[x].data["mosi"]
            digit = ''.join(format(x, '1b') for x in digit)
            print("Bin: " + digit[:4] + " " + digit[4:])

            foundDigit = "0"
            for number, pattern in numberPatterns.items():
                matchNumber = re.search(pattern, digit)
                if matchNumber:
                    foundDigit = number

            if foundDigit == "L":
                overload = True

            matchDot = re.search(dotPattern, digit)
            if matchDot:
                if idx == 3:
                    foundDigit = "-" + foundDigit
                else:
                    foundDigit = "." + foundDigit
            print("Str: " + foundDigit)
            outDigits.append(foundDigit)
        

        # Parse modes
        if self.isBitSet(bitFlags["Voltage"]):
            if self.isBitSet(bitFlags["DC"]):
                mode = "V DC"
            elif self.isBitSet(bitFlags["AC"]):
                mode = "V AC"

        if self.isBitSet(bitFlags["Current"]):
            if self.isBitSet(bitFlags["DC"]):
                mode = "A DC"
            elif self.isBitSet(bitFlags["AC"]):
                mode = "A AC"

        if self.isBitSet(bitFlags["Resistance"]):
            mode = "Ohm"

        if self.isBitSet(bitFlags["Temperature"]):
            mode = "°C"


        if self.isBitSet(bitFlags["AC"]):
            for idx in range(3,-1, -1):
                #print("idx: " + str(idx))
                digit = bytes()
                for x in range(41+8*idx, 41+8*(idx+1)):
                    #print("x: " + str(x))
                    digit += self.frames[x].data["mosi"]
                digit = ''.join(format(x, '1b') for x in digit)
                print("Bin2: " + digit[:4] + " " + digit[4:])

                foundDigit = "0"
                for number, pattern in numberPatterns.items():
                    matchNumber = re.search(pattern, digit)
                    if matchNumber:
                        foundDigit = number

                if foundDigit == "L":
                    overload = True

                matchDot = re.search(dotPattern, digit)
                if matchDot:
                    if idx == 3:
                        foundDigit = "-" + foundDigit
                    else:
                        foundDigit = "." + foundDigit
                print("Str2: " + foundDigit)
                outDigits2.append(foundDigit)
        
        # parse digits und denominator to a float
        if overload:
            parsed = "Overload!"
        else:
            parsed = "".join(outDigits)
            parsed = float(parsed)
            exponent = 0
            if self.isBitSet(bitFlags["Exponent_Milli"]): # milli
                exponent = -3
            elif self.isBitSet(bitFlags["Exponent_Micro"]): # micro
                exponent = -6
            elif self.isBitSet(bitFlags["Exponent_Kilo"]): # kilo
                exponent = 3
            elif self.isBitSet(bitFlags["Exponent_Mega"]): # mega
                exponent = 6
            parsed = parsed * 10**exponent

        if len(outDigits2) == 4:
            parsed2 = "".join(outDigits2)
            parsed2 = float(parsed2)
            if self.isBitSet(bitFlags["Exponent__Secondary_Kilo"]): # kilo for secondary display
                parsed2 = parsed2 * 10**3

        print("---")
        return {
            "mode": mode,
            "parsed": parsed,
            "parsed2": parsed2
        }

    def isBitSet(self, bit):
        return self.frames[bit].data["mosi"] == b'\x01'

    def handle_disable(self, frame):
        if self.is_valid_transaction():
            result = AnalyzerFrame(
                "LCD",
                self.transaction_start_time,
                frame.end_time,
                self.get_frame_data(),
            )
        else:
            result = AnalyzerFrame(
                "LCDError",
                frame.start_time,
                frame.end_time,
                {
                    "error_info": "Invalid SPI transaction (spi_enable={}, error={}, transaction_start_time={})".format(
                        self.spi_enable,
                        self.error,
                        self.transaction_start_time,
                    )
                }
            )

        self.reset()
        return result

    def handle_error(self, frame):
        result = AnalyzerFrame(
            "LCDError",
            frame.start_time,
            frame.end_time,
            {
                "error_info": "The clock was in the wrong state when the enable signal transitioned to active"
            }
        )
        self.reset()

    def decode(self, frame: AnalyzerFrame):
        if frame.type == "enable":
            return self.handle_enable(frame)
        elif frame.type == "result":
            return self.handle_result(frame)
        elif frame.type == "disable":
            return self.handle_disable(frame)
        elif frame.type == "error":
            return self.handle_error(frame)
        else:
            return AnalyzerFrame(
                "LCDError",
                frame.start_time,
                frame.end_time,
                {
                    "error_info": "Unexpected frame type from input analyzer: {}".format(frame.type)
                }
            )
