------------------------------------------------------------------------------
--                              Ada Web Server                              --
--                                                                          --
--                            Copyright (C) 2002                            --
--                                ACT-Europe                                --
--                                                                          --
--  Authors: Dmitriy Anisimkov - Pascal Obry                                --
--                                                                          --
--  This library is free software; you can redistribute it and/or modify    --
--  it under the terms of the GNU General Public License as published by    --
--  the Free Software Foundation; either version 2 of the License, or (at   --
--  your option) any later version.                                         --
--                                                                          --
--  This library is distributed in the hope that it will be useful, but     --
--  WITHOUT ANY WARRANTY; without even the implied warranty of              --
--  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU       --
--  General Public License for more details.                                --
--                                                                          --
--  You should have received a copy of the GNU General Public License       --
--  along with this library; if not, write to the Free Software Foundation, --
--  Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.          --
--                                                                          --
--  As a special exception, if other files instantiate generics from this   --
--  unit, or you link this unit with other files to produce an executable,  --
--  this  unit  does not  by itself cause  the resulting executable to be   --
--  covered by the GNU General Public License. This exception does not      --
--  however invalidate any other reasons why the executable file  might be  --
--  covered by the  GNU Public License.                                     --
------------------------------------------------------------------------------

--  $Id$

with Ada.Exceptions;
with Ada.Strings.Fixed;
with Ada.Strings.Maps.Constants;

package body AWS.Headers.Values is

   use Ada.Strings;

   Spaces : constant Maps.Character_Set
     := Maps.To_Set (' ' & ASCII.HT & ASCII.LF & ASCII.CR);
   --  Set of spaces to ignore during parsing

   procedure Next_Value
      (Data        : in     String;
       First       : in out Natural;
       Name_First  :    out Positive;
       Name_Last   :    out Natural;
       Value_First :    out Positive;
       Value_Last  :    out Natural);
   --  Returns the next named or un-named value from Data. It start the search
   --  from First index. Returns First = 0 if it has reached the end of
   --  Data. Returns Name_Last = 0 if an un-named value has been found.

   ------------
   --  Index --
   ------------

   function Index
     (S              : in Set;
      Name           : in String;
      Case_Sensitive : in Boolean := True)
      return Natural
   is
      Map    : Maps.Character_Mapping;
      Sample : Unbounded_String;
   begin
      if Case_Sensitive then
         Map := Maps.Identity;
         Sample := To_Unbounded_String (Name);
      else
         Map := Maps.Constants.Upper_Case_Map;
         Sample := Translate (To_Unbounded_String (Name), Map);
      end if;

      for I in S'Range loop
         if S (I).Named_Value
           and then Translate (S (I).Name, Map) = Sample
         then
            return I;
         end if;
      end loop;

      --  Name was not found, return 0
      return 0;
   end Index;

   ----------------
   -- Next_Value --
   ----------------

   procedure Next_Value
     (Data        : in     String;
      First       : in out Natural;
      Name_First  :    out Positive;
      Name_Last   :    out Natural;
      Value_First :    out Positive;
      Value_Last  :    out Natural)
   is
      EDel   : constant Maps.Character_Set := Maps.To_Set (",;");
      --  Delimiter between name/value pairs in the HTTP header lines.
      --  In WWW-Authenticate, header delimiter between name="Value"
      --  pairs is a comma.
      --  In the Set-Cookie header, value delimiter between name="Value"
      --  pairs is a semi-colon.

      UVDel  : constant Character := ' ';
      --  Delimiter of the un-named value

      NVDel  : constant Character := '=';
      --  Delimiter between name and Value for a named value

      VDel   : constant Maps.Character_Set := Maps.To_Set (UVDel & NVDel);
      --  Delimiter between name and value is '=' and it is a space between
      --  un-named values.

      Last   : Natural;

   begin
      Last := Fixed.Index (Data (First .. Data'Last), VDel);

      Name_Last := 0;

      if Last = 0 then
         --  This is the last single value.

         Value_First := First;
         Value_Last  := Data'Last;
         First       := 0; -- Mean end of line

      elsif Data (Last) = UVDel then
         --  This is an un-named value
         Value_First := First;
         Value_Last  := Last - 1;
         First       := Last + 1;

      else
         --  Here we have a named value

         Name_First := First;
         Name_Last  := Last - 1;
         First      := Last + 1;

         --  Check if this is a quoted or unquoted value

         if Data (First) = '"' then
            --  Quoted value

            Value_First := First + 1;

            Last := Fixed.Index (Data (Value_First .. Data'Last), """");

            if Last = 0 then
               --  Format error as there is no closing quote

               Ada.Exceptions.Raise_Exception
                 (Format_Error'Identity,
                  "HTTP header line format error : " & Data);
            else
               Value_Last := Last - 1;
            end if;

            First := Last + 2;

         else
            --  Unquoted value

            Value_First := First;

            Last := Ada.Strings.Fixed.Index (Data (First .. Data'Last), EDel);

            if Last = 0 then
               Value_Last := Data'Last;
               First      := 0;
            else
               Value_Last := Last - 1;
               First      := Last + 1;
            end if;
         end if;
      end if;

      if First > Data'Last then
         First := 0;

      elsif First > 0 then
         --  Ignore the next leading spaces

         First := Fixed.Index
            (Source => Data (First .. Data'Last),
             Set    => Spaces,
             Test   => Outside);
      end if;
   end Next_Value;

   -----------
   -- Parse --
   -----------

   procedure Parse (Header_Value : in String) is

      First       : Natural;
      Name_First  : Positive;
      Name_Last   : Natural;
      Value_First : Positive;
      Value_Last  : Natural;
      Quit        : Boolean;

   begin
      --  Ignore the leading spaces

      First := Fixed.Index
        (Source => Header_Value,
         Set    => Spaces,
         Test   => Outside);

      if First = 0 then
         --  Value is empty or contains only spaces
         return;
      end if;

      loop
         Next_Value
           (Header_Value, First,
            Name_First,  Name_Last,
            Value_First, Value_Last);

         Quit := False;

         if Name_Last > 0 then
            Named_Value
              (Header_Value (Name_First .. Name_Last),
               Header_Value (Value_First .. Value_Last),
               Quit);
         else
            Value
              (Header_Value (Value_First .. Value_Last),
               Quit);
         end if;

         exit when Quit or else First = 0;

      end loop;
   end Parse;

   -----------
   -- Split --
   -----------

   function Split (Header_Value : in String) return Set is

      First    : Natural;
      Null_Set : Set (1 .. 0);

      function To_Set return Set;
      --  Parse the Header_Value and return a set of named and un-named
      --  value. Note that this routine is recursive as the final Set size is
      --  not known. This should not be a problem as the number of token on an
      --  Header_Line is quite small.

      ------------
      -- To_Set --
      ------------

      function To_Set return Set is

         Name_First  : Positive;
         Name_Last   : Natural;
         Value_First : Positive;
         Value_Last  : Natural;

         function Element return Data;
         --  Returns the Data element from the substrings defined by
         --  Name_First, Name_Last, Value_First, Value_Last.

         -------------
         -- Element --
         -------------

         function Element return Data is
            function "+"
              (Item : in String)
               return Unbounded_String
              renames To_Unbounded_String;
         begin
            if Name_Last = 0 then
               return Data'
                 (Named_Value => False,
                  Value => +Header_Value (Value_First .. Value_Last));
            else
               return Data'
                  (True,
                   Name  => +Header_Value (Name_First .. Name_Last),
                   Value => +Header_Value (Value_First .. Value_Last));
            end if;
         end Element;

      begin
         if First = 0 then
            -- This is
            return Null_Set;
         end if;

         Next_Value
           (Header_Value, First,
            Name_First,  Name_Last,
            Value_First, Value_Last);

         return Element & To_Set;
      end To_Set;

   begin
      First := Fixed.Index
        (Source => Header_Value,
         Set    => Spaces,
         Test   => Outside);

      return To_Set;
   end Split;

end AWS.Headers.Values;
